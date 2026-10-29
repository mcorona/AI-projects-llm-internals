# Week 13: agentic patterns (workflows vs agents) and the Claude Agent SDK

Status: in progress.

Phase 4 (weeks 13 to 18) covers agents, MCP and orchestration. This week takes one LegacyBridge flow (question → explore schema and business rules → SQL → validate → run read-only → answer with evidence) and implements it in two patterns: a **workflow** with fixed steps and an **agent** built with the Claude Agent SDK. Both use the same tools, and they are compared on success, cost, latency, consistency and safety with the same frozen gold set. Evaluator-optimizer and orchestrator-workers are measured on a subset.

Everything runs locally: the legacy schema from week 10 (`legado`, views with cryptic names over the inventory-copilot data) and the read-only role `copilot_ro`. The only cost is the Anthropic API.

## 1. Task gold set (ES/EN), frozen

Built by [`golden/construir_tareas.py`](golden/construir_tareas.py) and validated against the database with the read-only role. Files:
- `golden/tareas_es.jsonl` and `golden/tareas_en.jsonl`.
- `golden/reglas_negocio.json`.
- `golden/manifiesto.json`, with counts, the data snapshot and SHA-256 hashes.

**42 tasks per language:**

| Type | Tasks | What it tests | Expected state |
|---|---|---|---|
| Simple | 10 | Questions from the week 7 hard set | answered |
| Business rules | 12 | Coverage days, critical SKUs at risk, escalation levels, reorder point by policy, alternate supplier, purchase proposals and their approval level, three quotes, surplus by distribution center, ABC class | answered |
| Compound | 8 | Several sub-questions that combine rules (for example, at-risk SKUs with a surplus to transfer before buying) | answered |
| Value traps | 4 | The question uses words that are stored differently ("Tornillería", "Estados Unidos", "Hidráulica", the city of a distribution center) | answered |
| Ambiguous | 4 | Missing criterion, SKU or distribution center | needs clarification |
| No answer in the data | 4 | Margin, customers, OTIF, in-transit units | abstained |

**Business rules.** [`golden/reglas_negocio.json`](golden/reglas_negocio.json) has 15 rules taken from the inventory-copilot documents (reorder policy, critical SKUs, purchase orders, transfers between distribution centers, cycle counting). Each rule states how it is computed on the schema. Examples:
- The cutoff date is the last date with sales, not today.
- Average daily sales count days without sales as zero.
- A purchase proposal is generated for every SKU below its reorder point with no open order.

These rules are what the `buscar_regla_negocio` tool will return.

**Expected results.** Each answerable task defines its output as named keys. There are 44 keys, each of type rows, set, number or text. Each key has a reference SQL over the original tables, and its expected result comes from running that SQL against the database. The agent reports, for each key, the SQL that produces it and the value.

The evaluation reruns that SQL with the read-only role and compares it with the expected result using the week 7 comparator. It measures two things:
- **Execution accuracy:** whether the key's SQL returns the expected result.
- **Answer consistency:** whether the value the agent reports matches the data.

**Validation (2026-10-29):**
- Data snapshot: cutoff 2026-09-26; 200 products, 600 stock rows, 36,000 daily sales rows, 12 suppliers and 1 purchase order.
- Every reference SQL runs.
- Number and text keys return exactly one value.
- No expected result is empty or zero.

**What the first validation found.** The purchase orders table holds a single order. Tasks about approval levels and quotes on existing orders, and escalation level 3 (no critical SKU at zero), all returned zero, so they did not discriminate. They were replaced with the same rules applied to the **purchase proposals** that the reorder policy generates on the cutoff date. Those are 24 proposals for $1,436,118.17: 19 for the buyer, 4 for the purchasing manager and 1 for the operations director.

## 2. Shared tools with a contract

[`herramientas/herramientas.py`](herramientas/herramientas.py) defines the five tools that every pattern uses, so the patterns differ only in orchestration:

| Tool | What it does |
|---|---|
| `describir_esquema` | Tables and columns the user can read, with the data dictionary. The original names are not revealed |
| `buscar_regla_negocio` | Business rules by keywords (Spanish or English) or by id, with the exact definition to compute |
| `muestrear_valores` | Most frequent distinct values of a column, to check how data is stored before filtering |
| `validar_sql` | The guard plus `EXPLAIN`, without running the query |
| `ejecutar_sql` | Guard, then a read-only transaction that is always rolled back, with time and row limits |

**Contract**
- **Inputs:** Pydantic models with `extra="forbid"`. The JSON Schema of every tool has `additionalProperties: false`, required fields, an enum of tables and bounds (`max_filas` ≤ 200). A model that sends `roles`, or any other field the system did not give it, gets `argumentos_invalidos`.
- **Outputs:** always JSON, never an exception: `{"ok": true, ...}` or `{"ok": false, "error": {"tipo", "mensaje", "sugerencia"}}`. Database errors carry a hint per SQLSTATE: missing column, GROUP BY, division by zero, invalid value format.
- **Summarized outputs:**
  - Rows up to `max_filas`, with the real total and a `truncado` flag.
  - Long texts are cut, and each response is capped at 6,000 characters.
  - An empty result carries a note that points to `muestrear_valores` and `buscar_regla_negocio`.
- **Trace:** every call is logged in the context with its tool, arguments, result and milliseconds.

**Permissions are injected by the system.** [`herramientas/permisos.json`](herramientas/permisos.json) defines four synthetic roles (`almacen`, `ventas`, `compras`, `finanzas`), the tables each one can read, and one restricted column (`art_cst`, unit cost, for `compras` and `finanzas`). The `Contexto` that holds the user and roles is created by the system; no tool parameter carries them.
- `describir_esquema` hides what the user cannot read.
- The guard rejects tables, columns and `SELECT *` that would expose them.

The gold set runs as `analista`, who can read everything.

**Guard (sqlglot, PostgreSQL dialect)**
- Exactly one statement, and the root must be SELECT or a set operation.
- No writes, including `SELECT INTO`, `FOR UPDATE`, `SET` and DDL.
- No dangerous functions (`lo_*`, `pg_*`, `set_config`, `current_setting`, `nextval`, `dblink`…).
- Only the `legado` schema, and only tables and columns allowed to the user. CTE names are recognized.

**Defense in depth.** Underneath the guard, the session uses the `copilot_nlq` role from week 10: `SELECT` only on the `legado` views and read-only by default. It is recreated with a random per-session password that is not stored ([`herramientas/conexion.py`](herramientas/conexion.py)). Each query runs in a `READ ONLY` transaction that is always rolled back, with `statement_timeout`.

**Tests:** [`tests/test_herramientas.py`](tests/test_herramientas.py) has 62 tests, and all pass against the local database.
- **Contract:** strict schemas, invalid arguments (including a model trying to pass `roles`) and unknown tools.
- **Rules:** search in both languages and lookup by id.
- **Guard:** 22 cases and 6 permission cases by user.
- **Database:**
  - Execution, truncation and the empty-result hint.
  - Sampling, `EXPLAIN` with a missing column, and database errors with hints.
  - A timeout at 200 ms.
  - The role has no write privilege, and `lo_create`, `DELETE` and `CREATE TEMP` still fail when the guard is bypassed.
  - The tool reproduces gold task `s03`.

Dependencies added: `sqlglot` and `pytest` (dev).

## 3. Own agentic loop

[`agente/loop.py`](agente/loop.py) implements tool use directly on the Anthropic Messages API, with no framework. The model asks for tools, the system runs them (the activity 2 tools) and returns `tool_result` blocks, until the model calls `responder` or a limit is reached.

| Requirement | Implementation |
|---|---|
| Tool use loop | `Agente.resolver(tarea)` sends the system prompt, the six tools (five plus `responder`) and the conversation; it runs every `tool_use` block and appends the results |
| Parallel calls | When the model requests several tools in one turn, all of them run and their results go back together in one user message, each with its `tool_use_id`. They run in order because they share the database connection |
| Bounded retry | A tool error goes back to the model with `is_error` and the tool's suggestion. After 3 consecutive errors the loop stops. Transient API errors (429, 5xx, 529) are retried with exponential backoff |
| Stop with a state | The model chooses `respondida`, `requiere_aclaracion` or `abstenida`. The system sets `limite_alcanzado` (12 model calls, 30 tool calls, 200k tokens, 180 s, consecutive errors, or no `responder` after one reminder) or `error` (API) |
| Structured final answer | [`agente/respuesta.py`](agente/respuesta.py): `RespuestaFinal` (Pydantic, `extra="forbid"`) with state, answer, `resultados` (key, SQL, value), evidence (rows or rule cited), assumptions and a clarification question. It is the JSON Schema of `responder`. `revisar_final` adds checks that depend on the task: one entry per output key, no parameters serialized inside a text field, a question when clarification is required. A failed check goes back to the model as `respuesta_invalida` |
| JSONL traces per step | One event per model call (tokens, cost, ms, stop reason, tools requested), per tool (arguments, ok or error type, parallel flag, ms, output size), per final answer and per stop (state, reason, totals) |

**Verification** ([`agente/verificar.py`](agente/verificar.py)).
- **Execution accuracy per key:** the SQL the agent reports for each key goes through the guard and is re-executed in full, then compared with the expected result using the week 7 comparator.
- **Consistency per key:** the value the agent reports must match what its own SQL returns.
- **Task success:** the right state and, when an answer is expected, every key exact.

**Tests.** [`tests/test_loop.py`](tests/test_loop.py) has 15 tests with a scripted fake API. They cover:
- Parallel calls returned together.
- The request body.
- A tool error returned and corrected.
- The bounded retry.
- Each limit (steps, tools, tokens).
- The reminder when the model does not call `responder`.
- Invalid or incomplete final answers sent back.
- `responder` mixed with other tools.
- Clarification and abstention.
- API errors.
- The `responder` schema.

The week has 77 tests in total.

**Pilot** (Haiku 5.5, effort `low`, one task of each type in ES and EN, 12 runs):

| Run | Success | Key consistency | Model calls (min. steps 32) | Tool calls (in parallel turns) | Tool errors | p50 per task | Cost |
|---|---|---|---|---|---|---|---|
| `piloto` | 10/12 | 0.875 | 45 | 66 (42) | 0 | 8.3 s | $0.0361 |
| `piloto2`, after the two fixes | **12/12** | **1.000** | 43 | 65 (43) | 0 | 6.0 s | $0.0334 |

The first pilot found two real problems:
- **`c02-es`: an ambiguous rule.** `R-PROPUESTA` said "its reorder point", and the agent used the policy-recalculated point instead of the recorded one. It got 16/3/1 proposals instead of 19/4/1. The rule now names `artmst.art_ptr` explicitly. The expected values do not change; the rules hash in the manifest is updated.
- **`r02-en`: a malformed final answer.** The 11 SKUs were correct, but Haiku serialized `resultados` inside the `respuesta` text (`</respuesta><parameter name="resultados">…`) and left the list empty. The JSON Schema cannot catch this because it does not know each task's keys. `revisar_final` now rejects it and sends it back to the model.

Files:
- Detail per task: `resultados/piloto_detalle.jsonl` and `resultados/piloto2_detalle.jsonl`.
- Traces: `resultados/trazas/piloto.jsonl` (135 events) and `resultados/trazas/piloto2.jsonl` (132 events).
- Runner: [`agente/correr.py`](agente/correr.py). It prints the worst-case cost and stops at a cost cap.

The full evaluation (all 84 tasks, k = 3) is activity 6.
