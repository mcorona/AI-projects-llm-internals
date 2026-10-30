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
