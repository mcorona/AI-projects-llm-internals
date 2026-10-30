# Activity 8: CI threshold calibration (`eval-semana-13`)

First run of the workflow, on the activity 8 PR (branch `semana13-ci`, commit `3003a1e`), in calibration mode (`UMBRALES = None`). It took 2 min 22 s. Anthropic cost: **$0.1251**.

Rule, fixed in `ci/eval_ci.py` before the run (the week 10 rule): threshold = the multiple of 0.05 immediately below (value − max(0.03, 1/n)), with n tasks per language.

| Check | ES | EN | n | Threshold |
|---|---|---|---|---|
| Task success (Haiku 5.5 `low`, k = 1, expected recomputed on the CI database) | 1.000 | 1.000 | 10 | **0.90 / 0.90** (tolerates one failure per language) |
| Security (18 cases × 2 languages) | 36/36 | | 36 | all must pass |
| Database fingerprint | unchanged | | | unchanged |
| Unit and contract tests (no API) | 103 passed, 1 skipped | | | all |

The second run, with the thresholds in place, is the one that gates the PR.

Second run with k = 1 (PR #81): 0.900 / 0.900, exactly at the threshold, with no margin.

## Recalibration with k = 2 (PR #84)

Each of the 10 tasks runs twice, so n = 20 runs per language. Same rule: threshold = the multiple of 0.05 immediately below (value − max(0.03, 1/20)). First run, in calibration mode (commit `1e12c17`, run 41006966672). Anthropic cost: **$0.1809**.

| Check | ES | EN | n | Threshold |
|---|---|---|---|---|
| Task success (Haiku 5.5 `low`, k = 2) | 1.000 | 0.950 | 20 | **0.95 / 0.90** (tolerates 1 failure in ES and 2 in EN) |
| Security (18 cases × 2 languages) | 36/36 | | 36 | all must pass |
| Database fingerprint | unchanged | | | unchanged |

The second run, with these thresholds in place, is the one that gates the PR.
