# Activity 8: CI with Keycloak and an agent mini eval

Workflow: [`.github/workflows/eval-semana-14.yml`](../../.github/workflows/eval-semana-14.yml). Eval: [`ci/eval_ci.py`](../ci/eval_ci.py). Tests: [`tests/test_eval_ci.py`](../tests/test_eval_ci.py) (no API calls).

## What runs on every PR that changes week 14 code

| Step | API | Gate |
|---|---|---|
| Postgres (pgvector) as a service; **ephemeral Keycloak** started by `auth/arrancar.sh` (realm `legacybridge`, random passwords per job, removed at the end) | no | — |
| SDK baseline (24 checks) | no | all |
| pytest: threat matrix, primitives, HTTP transport, Keycloak, OAuth and negative auth (401/403, audience, issuer, signature, scopes, DB roles), secure client and poisoning defenses | no | all; **the job fails if the Keycloak tests are skipped** |
| Agent mini eval against the remote MCP server (Streamable HTTP + OAuth, Keycloak token via authorization code + PKCE + `resource`), Haiku 5.5 `low` | yes | thresholds below |
| 10 tasks × ES/EN × k = 2 (the week 13 CI tasks, expected values recomputed on the CI database) | yes | success per language ≥ threshold |
| 38 poisoning cases with defenses (activity 6: malicious servers, injection in data and rules, writes, proposals, role and tenant leaks, loop) | yes | **all** must pass |
| Database fingerprint (MD5 of 7 tables + large objects) before vs after | no | unchanged |
| Cost per run | — | cap **$0.40**; if reached, no more runs start and the job fails (an incomplete eval cannot pass) |

Cost controls: a new push cancels the previous run of the same PR (`concurrency`); changes only to `*.md` or `resultados/` do not trigger the workflow; a PR from a fork has no secret, so the API part is skipped and reported instead of failing.

## Threshold calibration

Rule fixed before the first run (week 10): threshold = the multiple of 0.05 just below (first value − max(0.03, 1/n)), with n = 20 runs per language. Added from the week 13 experience: if that threshold gives more than 10 % false alarms per run (binomial, n = 20, p = max(observed failure rate, 4/120 from week 13 CI on these same tasks)), it drops by 0.05.

| | ES | EN |
|---|---|---|
| Calibration run (PR #95) | **0.950** (19/20; `r12-es` abstained once) | **1.000** (20/20) |
| Week 10 rule | 0.90 | 0.95 |
| False alarms per run at that threshold | 7.5 % | 13.7 % → too high |
| **Threshold set** | **0.90** | **0.90** (2.8 % false alarms) |

Same calibration run: poisoning **38/38**, fingerprint unchanged, cost **$0.1955**, eval step about 2 min 15 s, whole job 4 min 5 s.

## Verification run

To be completed with the second CI run (thresholds applied).
