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

## 4. MCP server with the same tools

[`servidor_mcp/servidor.py`](servidor_mcp/servidor.py) is an MCP server over stdio, built on the official Python SDK, pinned to `mcp==2.3.0`. That version has a new API: `on_list_tools` and `on_call_tool` handlers in the constructor, and types in `mcp_types`.
- **Same catalog:** it announces `definiciones()` unchanged (names, descriptions and JSON Schema).
- **Same implementation:** every call runs through `Herramientas.llamar`, so the guard, permissions, limits and structured errors are shared code, not a copy.
- **Response format:** each response carries the JSON as text, `structured_content`, and `is_error` when the tool failed.
- **Permissions:** the host that registers the server sets the user with `MCP_USUARIO` (default `analista`). The model never does: a `usuario` or `roles` argument gets `argumentos_invalidos`.

[`servidor_mcp/cliente.py`](servidor_mcp/cliente.py) (`HerramientasMCP`) is an MCP client with the same interface as the native tools (`llamar`, `definiciones`). The agent takes its catalog from whichever source it gets, so the loop does not change. `agente/correr.py --via mcp` runs the agent through the server. The SDK is async (anyio) and the loop is sync: the client runs its own event loop in a thread, and a single task opens the session, serves requests from a queue and closes it.

**Equivalence on the gold set** ([`resultados/mcp_equivalencia.md`](resultados/mcp_equivalencia.md); deterministic, no model calls):

| Check | Result |
|---|---|
| A. `tools/list` equals `definiciones()` | yes |
| B. Every tool call from the pilot traces, replayed through both paths in its task's language | 107/107 identical |
| C. The SQL of every gold key from pilot 2, run through both paths | 12/12 identical, 12/12 exact against the gold set |
| D. Permissions and errors: 3 users (`analista`, `almacenista`, `vendedor`) × 13 cases (schema by role, restricted column, `SELECT *`, other schema, writes, `set_config`, `roles` argument, database error) | 39/39 identical |

**The agent through MCP** (same 12 pilot tasks, Haiku 5.5 `low`):

| Tools | Success | Key consistency | Tool calls | p50 per task | Cost |
|---|---|---|---|---|---|
| Native (`piloto2`) | 12/12 | 1.000 | 65 | 6.0 s | $0.0334 |
| MCP (`piloto_mcp`) | **12/12** | **1.000** | 60 | 7.2 s | $0.0318 |

The MCP path adds about one second per task: process spawn and JSON-RPC over stdio. The tool results are identical (check B), so any difference between the two runs comes from sampling, not from the path.

**MCP Inspector** (CLI mode, `npx @modelcontextprotocol/inspector --cli … uv run python semana-13/servidor_mcp/servidor.py`):
- `tools/list` returns the five tools.
- `buscar_regla_negocio consulta=cobertura` returns `R-COB`.
- `ejecutar_sql` with a `GROUP BY` returns 7 rows by country.
- `ejecutar_sql "DELETE FROM exidet"` returns `escritura_bloqueada`, and the Inspector reports `tool_is_error` (`isError: true`).

**Claude Code:** the server is registered in [`/.mcp.json`](../.mcp.json) as `legado-semana13` (stdio, `uv run python semana-13/servidor_mcp/servidor.py`). It takes `PG_DSN` from the environment, so there are no credentials in Git, and it was approved for the project. The local approval file (`.claude/settings.local.json`) is git-ignored.

**Tests:** [`tests/test_mcp.py`](tests/test_mcp.py) spawns the server over stdio and checks four things: the catalog is identical, 11 cases give the same response for 2 users, permissions are set by the host, and the protocol's `is_error` is set. Against the database, the same execution in 4 cases. The week has 95 tests.

## 5. Agent evaluation

The own agentic loop was run on the full gold set (42 tasks × 2 languages = 84 tasks), k = 3 independent runs per task, with Haiku 5.5 at effort `low` and `medium`. Sonnet 5.5 `low` was run on the subset where Haiku fell short.
- Report: [`resultados/agente.md`](resultados/agente.md), built by [`agente/evaluar.py`](agente/evaluar.py) from the run details and traces.
- Machine-readable: [`resultados/agente_resumen.json`](resultados/agente_resumen.json).
- Confidence intervals: 95 %, bootstrap over tasks. Differences between configurations use a paired bootstrap by task.

| Configuration | Runs | pass@1 [95 % CI] | pass^3 [95 % CI] | Key accuracy | Correct clarification | Correct abstention | p50 / p95 per task | Cost |
|---|---|---|---|---|---|---|---|---|
| Haiku 5.5 `low` | 252 | **0.921** [0.861, 0.972] | **0.905** [0.833, 0.964] | 0.970 | 0.500 | 1.000 | $0.0026 / $0.0052 · 7.1 / 14.8 s | $0.72 |
| Haiku 5.5 `medium` | 252 | 0.913 [0.849, 0.964] | 0.893 [0.821, 0.952] | 0.962 | 0.500 | 1.000 | $0.0031 / $0.0062 · 8.9 / 21.0 s | $0.88 |
| Sonnet 5.5 `low`, subset (a01–a04, c05; 10 tasks) | 30 | 1.000 | 1.000 | 1.000 | 1.000 | — | $0.0173 / $0.0393 · 3.7 / 7.8 s | $0.56 |

**What the numbers say**
- **`medium` buys nothing on this set.** The paired difference with `low` is −0.008 [−0.032, 0.016]. It costs about 20 % more and its p95 latency is 42 % higher. `low` is the default.
- **Haiku fails on clarification.** It asks for clarification on only half of the ambiguous tasks, with either effort. On a03 ("give me the products with low inventory") and a04 ("how much inventory do we have at *the* distribution center?") it picks an interpretation and answers, 12 of 12 times. It never asks for clarification or abstains on a task that has an answer, and it abstains correctly 100 % of the time.
- **Sonnet 5.5 `low` fixes both weak spots** on the subset: 30 of 30. Clarification goes from 0.500 to 1.000, and it avoids the c05 rounding error. Against Haiku `low`, the paired difference is +0.533 [0.233, 0.800]. It costs about 7 times more per task, but it needs fewer model calls (p50 2 instead of 4) and is faster (3.7 s p50).
- **Trajectory:**
  - 100 % of tool calls are valid (the tool exists and the arguments pass the schema), and 98.8 % to 99.8 % succeed.
  - The agent uses 1.56 times the minimum number of model calls with `low` and 1.73 times with `medium`.
  - There are no redundant calls (same tool and arguments twice in one run).
  - Runs with a tool error recover and end successfully 90.5 % of the time with `low` and 81.8 % with `medium`.
- **Free text, judged:** a Haiku 5.5 `low` judge grades only the clarification question or the abstention explanation, against the reason in the gold set. It was validated first on 2 good and 2 bad known cases, and got 4/4.
  - Haiku: 35/36 adequate with `low` and 33/36 with `medium`.
  - Sonnet: 20/24. The judge is strict: it marks a question as not adequate when it asks for only one of the two missing pieces, for example the distribution center but not units versus value.

**Remaining failures are real agent errors**
- **a03 and a04:** no clarification. This is a model behavior gap that Sonnet closes.
- **c05, a silently wrong result (SWAR):**
  - **The error:** Haiku writes `1.5*(total/3.0)` instead of `1.5*total/3.0`. The rounding of `total/3.0` makes SKUs whose stock is exactly half of the total count as a surplus. The result is 34 in Mexico City instead of 32.
  - **How often:** 4 of 6 runs with `low` and 6 of 6 with `medium`.
  - **Why it is dangerous:** the agent's value always matches its own SQL, so nothing looks wrong without a reference.
- **s02 and s10 (intermittent):** extra rows or columns. One row per warehouse instead of one per SKU.
- **r03-en:** the escalation level 1 count, 2 of 3 runs.

**What the evaluation found in the instrument (fixed and re-run).** The first full run (v1, kept in `resultados/v1/` with its report `agente_v1.md`) had pass@1 0.762 (`low`). Most of its failures were not the agent's:
- **An ambiguous output key:** the `filas` key was described as "result rows", so the agent answered `SELECT COUNT(*) AS filas`.
- **An unstated result shape:** the agent returned a correct set as a single `ARRAY_AGG` row.
- **An ambiguous question:** r04's "reorder point according to the reorder policy" invited the recalculated point.
- **An ambiguous rule:** `R-ESCALA` did not say that levels are not exclusive.

Fixes:
- The key, question and rule were reworded; the expected values did not change.
- Each task now states the shape of each key's result: rows, one row per value with no arrays, or a single value.
- The first wording of the `filas` fix ("not a row count") broke s05 ("how many…?", expected 0). It was made neutral, and the 20 simple tasks were re-run. The intermediate run is in `resultados/v2_simples/`.
- **The judge:** it sometimes ran out of tokens and returned truncated JSON. It now gets 2,000 tokens and 3 attempts, and a judge failure is recorded as "no verdict" instead of penalizing the agent.

**Defect found in the tools at scale.** A query with an unterminated quote raised sqlglot's `TokenError`. That is not a `ParseError`, the only error the guard caught, so it reached the runner and stopped the first run at 248 of 252. The guard now catches every sqlglot error and returns `sql_invalido`. `Herramientas.llamar` also turns any unexpected exception into the structured error `error_interno`, which enforces the activity 2 contract (never an exception to the model). There are 3 new tests.

**Runner at scale.** [`agente/correr.py`](agente/correr.py) adds:
- `--k`: repetitions.
- `--paralelo`: one read-only connection per thread; the `copilot_nlq` password is created once per process.
- `--reanudar`: does not repeat finished (task, repetition) pairs.
- `--tope-usd`: a cap on the cumulative cost of the run.

Traces carry the task and repetition (`r02-es#1`) and are written under a lock.

**Cost of the activity:**
- Agent runs, all included: $4.07 (v1 $1.57, v2 with simple re-runs $1.94, Sonnet subset $0.56).
- Judge: about $0.02.
- **Total: about $4.10.**

## 6. Agent vs workflow

The week 10 assistant was run as a **workflow with fixed routing** on the same gold set, with k = 3 and Haiku 5.5 `low`, using the same execution-based verification. It was compared with the agent's activity 5 run (`eval_haiku_low`).
- Code: [`workflow/semana10.py`](workflow/semana10.py).
- Report: [`resultados/agente_vs_workflow.md`](resultados/agente_vs_workflow.md).

**How the workflow runs.** The steps are fixed in code:
1. Routing with `ruteo.clasificar`, the week 10 router prompt, to `sql`, `documental` or `mixta`.
2. On `sql` or `mixta`, the week 10 NLQ (DDL plus full dictionary, `NO_SQL` abstention) writes one query per output key. Each query runs once through `ejecutar_sql`, with no retries and no business-rule lookup, as in week 10.
3. The `documental` route produces text, not computed figures, so it counts as an abstention.

To compare only the orchestration, the NLQ gets the same output information as the agent: each key's description and the shape contract. The workflow has no clarification step.

| Task type | Tasks | Agent pass@1 / pass^3 | Workflow pass@1 / pass^3 | Agent − workflow [95 % CI] | USD per task p50, agent / workflow | Seconds p50 / p95, agent / workflow |
|---|---|---|---|---|---|---|
| simple | 20 | 0.967 / 0.950 | 0.950 / 0.950 | +0.017 [−0.100, +0.150] | $0.0022 / $0.0005 | 6.4 / 9.4 · 3.1 / 4.3 |
| business rules | 24 | 0.972 / 0.958 | 0.139 / 0.083 | **+0.833** [+0.694, +0.958] | $0.0033 / $0.0004 | 9.2 / 14.6 · 2.8 / 6.6 |
| compound | 16 | 0.917 / 0.875 | 0.250 / 0.250 | **+0.667** [+0.438, +0.875] | $0.0044 / $0.0012 | 12.1 / 16.9 · 8.4 / 11.2 |
| value traps | 8 | 1.000 / 1.000 | 1.000 / 1.000 | 0 | $0.0023 / $0.0003 | 5.2 / 6.8 · 2.5 / 4.9 |
| ambiguous | 8 | 0.500 / 0.500 | 0.000 / 0.000 | **+0.500** [+0.125, +0.875] | $0.0019 / $0.0004 | 5.1 / 13.0 · 2.8 / 3.8 |
| no answer in the data | 8 | 1.000 / 1.000 | 1.000 / 1.000 | 0 | $0.0011 / $0.0003 | 4.2 / 6.6 · 2.7 / 5.0 |
| **Total** | 84 | **0.921 / 0.905** | 0.504 / 0.488 | **+0.417** [+0.310, +0.528] | $0.0026 / $0.0004 | 7.1 / 14.8 · 3.0 / 9.4 |

Total cost for 252 runs each: agent $0.72, workflow $0.14.

**Why the workflow fails where it fails** (from its 252 runs; 0 tool errors)
- **Business rules:** 47 of 72 runs were routed `mixta` and the NLQ answered `NO_SQL`. The week 10 abstention prompt tells it not to approximate "policies, approvals", and without the rule definition it cannot compute "at risk" or "proposal". When it did write SQL (25 runs), it guessed the definition and 13 were wrong. For example, at-risk SKUs became "critical with stock ≤ reorder point".
- **Compound:** one query per part with no shared plan. The parts that depend on a rule fail the same way, and 13 runs abstained after a `mixta` route.
- **Ambiguous:** it has no way to ask. It answered 15 runs with an arbitrary interpretation and abstained on 9.
- **Simple, value traps, no-answer tasks:** the fixed pipeline is enough. The dictionary already carries the value formats ('DE', 'Tornilleria', the city of each distribution center), and the abstention prompt catches margin, customers, OTIF and transit.

**Decision**

| Task type | Use | Why |
|---|---|---|
| Direct data questions (single query, the dictionary is enough) | **Workflow** | Same success (0.950 vs 0.967, CI includes 0), about 4 times cheaper per task and twice as fast (p50 3.1 s vs 6.4 s) |
| Value formats and spelling | **Workflow** | 1.000 for both, at one seventh of the cost; the dictionary solves it |
| Data that does not exist | **Workflow** | 1.000 for both; the abstention prompt is enough |
| Business rules or company definitions | **Agent** | +0.833: it looks up the rule and applies it. The workflow abstains or guesses |
| Several sub-questions | **Agent** | +0.667: it plans across the parts and reuses intermediate results |
| Ambiguous requests | **Agent with a model that asks** (Sonnet 5.5 `low`: 1.000 on the subset, activity 5) | The workflow cannot ask; Haiku asks only half of the time |

**Recommended architecture (not yet measured).** Keep the workflow as the cheap path for direct data questions and escalate to the agent when the question uses a business term, has several parts or is ambiguous. The week 10 router is not enough as the escalation signal: it sent only 48 of 72 rule runs and 22 of 48 compound runs to `mixta`. A classifier that also detects business terms, multiple parts and ambiguity would be needed. The patterns of the coming activities (evaluator-optimizer, orchestrator-workers) are measured on these same task types.

Cost of the activity: $0.14 (workflow runs; the agent was not re-run).
