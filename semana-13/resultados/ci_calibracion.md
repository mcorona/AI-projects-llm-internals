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
| Task success (Haiku 5.5 `low`, k = 2) | 1.000 | 0.950 | 20 | rule: 0.95 / 0.90 |
| Security (18 cases × 2 languages) | 36/36 | | 36 | all must pass |
| Database fingerprint | unchanged | | | unchanged |

Second run with 0.95 / 0.90 (commit `640994f`, run 41007488161, $0.1905), no code change: ES **0.900**, EN 1.000, security 36/36, fingerprint unchanged, 106 passed and 1 skipped. The Spanish gate failed on noise.

False-alarm check, with the failure rate observed over the four CI runs (4 failures in 120 task runs, p ≈ 0.033) and n = 20 per language:

| Threshold | Failures tolerated | False alarm per language | Per run (2 languages) |
|---|---|---|---|
| 0.95 | 1 | 14.2% | 26.4% |
| 0.90 | 2 | 2.8% | 5.5% |

**Final thresholds: 0.90 / 0.90.** When the first run is 1.000, the week 10 rule leaves a single failure of margin, so its false-alarm rate has to be checked against the observed failure rate before the threshold is fixed. The next run, with 0.90 / 0.90, is the one that gates the PR.
