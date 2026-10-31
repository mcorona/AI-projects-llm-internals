# Activity 7: end-to-end agent against the remote server

Code: [`agente_remoto/correr.py`](../agente_remoto/correr.py) (harness) and [`tests/test_agente_remoto.py`](../tests/test_agente_remoto.py) (4 deterministic tests, no API calls).
Generated report: [`remoto.md`](remoto.md). Detail: [`remoto_detalle.jsonl`](remoto_detalle.jsonl) (88 runs). Summary: [`remoto_resumen.json`](remoto_resumen.json). Traces: `trazas/remoto.jsonl`.

## Setup

- **Agent:** the week 13 loop and its system prompt, unchanged; Haiku 5.5 `low`; answers checked by `verificar` (re-executes the SQL).
- **Remote path:** Streamable HTTP + OAuth (activity 5) on `127.0.0.1:8014`, consumed through `ClienteSeguro`. Each user gets a **real Keycloak token** via authorization code + PKCE (S256) + `resource` (RFC 8707). The server maps the token's scopes to a per-profile database role (`SET LOCAL ROLE`).
- **stdio path:** the same server as a subprocess (`python -m servidor --transporte stdio --usuario analista`).
- **Baseline:** week 13 in-process (k = 3, 120 runs on the same subset).
- **Golden subset:** 20 tasks per language, stratified by type (5 simple, 5 rule, 4 composite, 2 values, 2 ambiguous, 2 no-answer), fixed before the run, k = 1.
- **Without scope:** 4 tasks × 2 languages run by `almacenista` (no supplier scope) or `vendedor` (no purchase-order scope). Pass criterion, fixed before the run: ends in denial or abstention **and** no expected value appears in the answer **and** no successful read of a forbidden table.
- **Cost:** 88 runs, **$0.2443** (estimate $0.25, cap $0.35).

## Results

| Path | Runs | Success | 95% CI (Wilson) | Cost / task | p50 task (s) | p50 tool call (ms) | p95 tool call (ms) |
|---|---|---|---|---|---|---|---|
| In-process (week 13, k = 3) | 120 | 0.917 | 0.853 to 0.954 | $0.0028 | 6.88 | 2 | 10 |
| stdio | 40 | 0.900 | 0.769 to 0.960 | $0.0029 | 6.25 | 10.1 | 28.3 |
| **Remote: HTTP + OAuth** | 40 | **0.900** | 0.769 to 0.960 | **$0.0028** | 6.42 | 17.4 | 32.7 |

Without scope: **0/8 leaks**, 8/8 abstained after the server denied the data (`tabla_no_disponible`, `permiso_denegado`).

## Reading

1. **Same quality over the network.** Remote and stdio failed **exactly the same 4 runs** (`c05` and `a03`, both languages), and they are the same tasks that already failed in week 13 in-process (`c05-es` 3/3, `a03-es` 3/3, `a03-en` 3/3). The transport and the authorization layer introduced no new failure. With n = 40 the intervals overlap fully with the baseline; the claim is "no detectable degradation", not "equal".
2. **Same cost.** The tool schemas and results the model sees are identical across paths, so tokens per task do not change ($0.0028 vs $0.0028).
3. **What HTTP + OAuth costs in latency.**
   - Per tool call, measured by the client: **+7 ms p50** over stdio (17.4 vs 10.1) and +15 ms over in-process.
   - On the server, the front layer (JWT validation + MCP + tool + database) takes 11.2 ms p50 over 209 calls, so roughly 6 ms p50 is HTTP and client overhead.
   - Getting a token through the full PKCE flow takes 32–52 ms, once per user and session.
   - Per task (p50 ≈ 6.4 s, dominated by model calls) the overhead is **under 1%**, below run-to-run noise.
4. **Authorization fails closed, in the database.** All three profiles hold `legado:leer`, so the agent's `ejecutar_sql` is reachable and the HTTP layer correctly returns 200. The cut happens one layer below: the scope picks the database role, and the role has no grant on supplier or purchase-order data. The model saw a structured denial and abstained in 8/8; no forbidden value reached an answer. The HTTP `403 insufficient_scope` path (a tool whose scope the token lacks, such as `proponer_compra`) is covered deterministically by `tests/test_auth.py` (activity 5) and needs no model run.

## Findings

- **The language issue comes from week 13, not from the activity 6 defenses.** EN tasks were answered in Spanish in 18/20 remote runs and 18/20 stdio runs, **without** the secure-client envelope, and in week 13 in-process as well (117/126 EN runs contained Spanish). The cause is the Spanish system prompt and data. `verificar` checks values, not language, so success rates are unaffected. The activity 6 note was corrected. Planned fix: language rule placed last in the prompt plus a language check in the week 17 trajectory eval.
- **`c05` and `a03` are stable failures of the agent, not of the infrastructure** (composite rule with per-CEDIS threshold; ambiguous "low inventory" read as below reorder point). They belong to prompt/rule work, not to week 14.

## Optional: Claude Code as the MCP client

Not run in this activity (no API cost, manual). Steps and two expected risk points (`resource` parameter → `aud`, and the `localhost` vs `127.0.0.1` redirect) are in the activity notes; to be recorded when tested.
