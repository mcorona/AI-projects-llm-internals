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
