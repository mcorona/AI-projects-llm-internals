# Week 7: bilingual NLQ-Inventory evaluation (Spanish and English)

Goal: measure how accurately different LLMs translate natural-language questions into SQL over a legacy-style inventory database, in Spanish and in English, and what each correct answer costs.

## What is measured

- **Execution accuracy:** the predicted SQL and the reference SQL run in a read-only session; their result sets must match as multisets. Column order does not matter, and extra predicted columns are allowed.
- **Cost per correct answer:** input and output tokens times the model price, divided by the number of correct answers. Models without a verified price report no cost.
- **Breakdown by language and by failure type:** `sin_sql` (no valid SELECT), `error_ejecucion` (the database rejects the query), `resultado_distinto` (valid SQL, wrong result).

## Dataset

`datasets/nlq_bilingual.jsonl` has 200 lines: 100 unique questions, each in Spanish (`-es`) and English (`-en`). The questions are generated from templates over the synthetic data in `inventory-copilot` (seed 42). Each question has a reference SQL.

`run_eval.py --validar` runs every reference SQL and keeps only the questions that return rows. The result goes to `datasets/nlq_validado.jsonl`.

This set is held out for measurement only. Prompts are not tuned on it.

## Files

| File | Purpose |
|---|---|
| `build_dataset.py` | Generates the bilingual dataset from templates |
| `build_hard_dataset.py` | Hand-written harder set: 48 questions, bilingual |
| `schema_completo.sql` | Full schema snapshot (`inventory-copilot` files 01 to 03), without roles or grants |
| `datasets/` | Question sets, and their validated versions (`*_validado.jsonl`) |
| `schema.sql` | Schema given to the model (trimmed to the columns the questions use) |
| `run_eval.py` | Runs validation, generates SQL with each model, executes it, compares results and reports. Flags: `--set facil\|dificil\|seguimiento`, `--esquema corto\|completo`, `--citas`, `--sin-historial` |
| `prices.json` | Prices per million tokens, with the source of each figure. `null` means unverified |
| `resultados/` | Per-question detail and per-model summary, one file per run |

## How to run

The database must be running. From `inventory-copilot`, start PostgreSQL with `docker compose up -d`.

From the repo root:

```bash
# Read-only DSN: the copilot_ro role from inventory-copilot/.env (not printed)
export NLQ_DSN="$(grep '^PG_DSN=' ~/inventory-copilot/.env | cut -d= -f2-)"

uv run python semana-07/run_eval.py --validar

uv run python semana-07/run_eval.py --modelos \
  anthropic:claude-haiku-5-5 \
  openai:gpt-5.6-luna \
  openai:gpt-5.6-terra \
  gemini:gemini-3.8-flash
```

API keys are read from the environment or from `semana-05/.env`, as in week 5.

## Design decisions

- **The model sees only the schema and the question.** No examples from the dataset are included, so the questions are not leaked into the prompt.
- **Read-only execution.** Every query runs in a read-only session with a 5-second timeout. Only one SELECT or WITH statement is accepted.
- **The comparator is adapted from `inventory-copilot`.** It is copied, not imported, so this week does not depend on that repository's code.
- **Reference SQL is validated first.** Questions whose reference returns no rows are dropped, so an empty result cannot count as a correct answer.

## Limits

- The questions are template-generated, so they are less varied than real user questions.
- One run per model is a single sample. Compare differences only when they are large relative to the number of questions.
- Prices come from a third-party source for OpenAI. Gemini has no verified price yet, so its cost is not reported.
- The system prompt is short, so prompt caching is not expected to apply.

## Results (final run, 100 questions per language)

Run date: 2026-10-22. Dataset validated: 200 of 200 lines.

| Model | Language | Execution accuracy | Cost (USD, this run) | Cost per correct answer (USD) |
|---|---|---|---|---|
| claude-haiku-5-5 (Anthropic) | EN | 100 / 100 | 0.0034 | 0.000034 |
| claude-haiku-5-5 (Anthropic) | ES | 100 / 100 | 0.0039 | 0.000039 |
| gemini-3.8-flash (Google) | EN | 100 / 100 | not verified | not verified |
| gemini-3.8-flash (Google) | ES | 100 / 100 | not verified | not verified |
| gpt-5.6-luna (OpenAI) | EN | 100 / 100 | 0.0733 | 0.000733 |
| gpt-5.6-luna (OpenAI) | ES | 100 / 100 | 0.0755 | 0.000755 |
| gpt-5.6-terra (OpenAI) | EN | 100 / 100 | 0.1511 | 0.001511 |
| gpt-5.6-terra (OpenAI) | ES | 100 / 100 | 0.1516 | 0.001516 |

Costs use the prices in `prices.json`. OpenAI prices come from a third-party source and are not verified. Gemini has no verified price.

**Reading these results.** Every model answered every question correctly, in both languages. This set does not separate the models, so it cannot rank their accuracy. The only useful difference in this run is cost: Haiku was the cheapest per correct answer, and gpt-5.6-terra was the most expensive.

## Public results: NLQ-Inventory, harder set

This is the table that discriminates between models. The easy set above is saturated, so it cannot rank them. Run: short schema (`schema.sql`), no citations, 43 valid questions per language. Costs come from the run summary, which rounds costs to four decimals.

| Model | Language | Execution accuracy | Cost (USD) | Cost per correct answer (USD) |
|---|---|---|---|---|
| claude-haiku-5-5 | EN | 43 / 43 (1.000) | 0.0040 | 0.000093 |
| claude-haiku-5-5 | ES | 41 / 43 (0.953) | 0.0057 | 0.000138 |
| gemini-3.8-flash | EN | 41 / 43 (0.953) | not verified | not verified |
| gemini-3.8-flash | ES | 41 / 43 (0.953) | not verified | not verified |
| gpt-5.6-luna | EN | 42 / 43 (0.977) | 0.0483 | 0.001150 |
| gpt-5.6-luna | ES | 43 / 43 (1.000) | 0.0506 | 0.001177 |
| gpt-5.6-terra | EN | 42 / 43 (0.977) | 0.0949 | 0.002260 |
| gpt-5.6-terra | ES | 41 / 43 (0.953) | 0.0964 | 0.002352 |

Single run per model, so differences of one or two questions are within noise. Costs use `prices.json`. OpenAI prices come from a third-party source and are not verified. Gemini has no verified price.

## Changes made during the evaluation

These changes were made after the first runs, and they apply equally to every model. The earlier runs are kept in `resultados/previos/`.

1. **Output limit raised to 4,096 tokens.** At 1,024 tokens, gemini-3.8-flash was cut off mid-query, because its reasoning tokens count toward the output limit.
2. **NULL counts as 0 in the comparator.** `SUM` without `COALESCE` returns NULL on empty sets; the reference uses `COALESCE(..., 0)`. Both now compare as 0.
3. **Wording of the stock question.** "Stocked" was ambiguous: the reference counts any stock record, while one model counted only positive stock. The question now says "stock record".
4. **Top-N SKU questions return only the SKU.** The questions ask for SKUs, so the reference no longer returns the total as an extra column that the comparator would require.
5. **Ties broken deterministically.** Ranking queries add `p.sku` as a tie-breaker, and one ambiguous supplier-ranking question was replaced with a count.
6. **Retries and error categories.** Network and server errors are retried up to three times. Quota and billing errors (4xx other than 429) are not retried and are recorded as `error_api`.

## Second iteration: harder set, citations, full schema, follow-ups

Every run writes `set`, `esquema`, `citas` and `sin_historial` into its summary, so each file records its own configuration. Each run is a single pass per model.

### Harder set (`--set dificil`)

- 48 hand-written questions in Spanish and English (`build_hard_dataset.py`). Each question states its own tie-break and rounding rule. They cover multi-table joins, correlated subqueries, anti-joins, window functions, date windows and `HAVING` thresholds.
- Validation keeps 86 of 96 lines, which is 43 questions per language. The discarded questions are `hard-013`, `018`, `023`, `030` and `046`. Their reference SQL returns no rows, mostly because of the data (for example, every product has sales). Two more questions with empty results were removed after the runs (see Changes).
- Result with the short schema (`schema.sql`) and no citations, correct out of 43 per language:

| Model | EN | ES |
|---|---|---|
| claude-haiku-5-5 | 43 | 41 |
| gemini-3.8-flash | 41 | 41 |
| gpt-5.6-luna | 42 | 43 |
| gpt-5.6-terra | 42 | 41 |

### Experiment 1: full schema (`--esquema completo`)

The full schema is the snapshot of `inventory-copilot/db/init` files 01 to 03, with roles, grants and passwords removed. It tests the effect of a longer context.

The first run was confounded. The snapshot had dropped the value hints that `schema.sql` carries (country codes, category names, city names), and the models then wrote `'Germany'` and `'China'`. The snapshot now carries the same hints. The confounded run is archived in `resultados/previos/` and is not used for any conclusion. The corrected run is recorded below.

### Experiment 2: citations (`--citas`)

The model lists the tables it read on a final `TABLES:` line. Correct answers stayed the same as without citations: claude-haiku-5-5 42/42, gemini-3.8-flash 42/41, gpt-5.6-luna 42/43, gpt-5.6-terra 42/42 (EN/ES).

- Exact match between cited and reference tables: 0.91 to 0.98.
- Precision: 0.97 to 0.99.
- Exhaustiveness: 0.99 to 1.00.

The reference tables come from a regex over the reference SQL, so the citation scores are a proxy, not a ground truth.

### Experiment 3: follow-up questions (`--set seguimiento`)

Twenty follow-up questions in each language. The previous turn is sent as an example in the conversation. The previous turn uses the reference SQL, so model errors do not carry into the next turn.

The first run, before the rewrites below, scored 154 of 160: claude-haiku-5-5 38/40, gpt-5.6-luna 38/40, gpt-5.6-terra 38/40, gemini-3.8-flash 40/40. The run is archived in `resultados/previos/`.

This score does not show that the previous turn is what makes the answers correct. The control is recorded below.

### Changes made during this iteration

1. **Full-schema snapshot corrected.** The first snapshot dropped the value hints from `schema.sql`. They are restored, and the confounded run is archived.
2. **Two follow-ups reworded to remove ambiguity (`seg-003`, `seg-016`, both languages).** The reference SQL did not change. The wording was changed after the first run had been read, and that run is archived as the before-state.
3. **Control flag added.** `--sin-historial` omits the previous turn.
4. **Follow-up `seg-011` reworded (after the results were read).** The follow-up "And what is its average unit cost?" was read by one model as the average over critical products only. The reference averages all products in the category. The wording now says "all products ... including the non-critical ones". The reference SQL did not change. The runs with the earlier wording are archived in `resultados/previos/`.
5. **Two empty-result questions removed.** The old `hard-039` (category "Seguridad") and `hard-040` (a threshold) returned no rows. Rather than correct them after seeing results, I removed them. Questions old `hard-041` to `048` were renumbered to `039` to `046`. The validated set was remapped by language and SQL, so the 43 valid questions per language are unchanged and the results above still apply. The earlier runs in `resultados/previos/` use the old numbering.

### Results after the corrected runs

Full schema, corrected snapshot, no citations. Correct out of 43 per language, with the short-schema results from the harder-set table above in the last column:

| Model | EN | ES | Short schema, no citations (EN / ES) |
|---|---|---|---|
| claude-haiku-5-5 | 43 | 42 | 43 / 41 |
| gemini-3.8-flash | 42 | 42 | 41 / 41 |
| gpt-5.6-luna | 41 | 43 | 42 / 43 |
| gpt-5.6-terra | 40 | 41 | 42 / 41 |

Across both languages, the totals move by −2 to +2 questions out of 86. That is within the noise of one run per model. The earlier drop came from the removed hints, not from the schema length. One run cannot show the schemas are equivalent, only that the difference is small.

Follow-up questions, rewritten wording. Correct out of 20 per language, with and without the previous turn (`--sin-historial`):

| Model | With history (EN / ES) | Without history (EN / ES) |
|---|---|---|
| claude-haiku-5-5 | 19 / 19 | 5 / 5 |
| gemini-3.8-flash | 20 / 20 | 4 / 4 |
| gpt-5.6-luna | 19 / 20 | 3 / 4 |
| gpt-5.6-terra | 18 / 19 | 4 / 4 |

The previous turn accounts for most of the answers: about 28 to 32 of 40 points per model. The 3 to 5 correct answers without it are probably follow-ups whose wording stands alone or matches by chance. I have not inspected them. The rewrite did not change the totals (before: 38, 40, 38, 38; after: 38, 40, 39, 37).

### Pending

- The follow-up table above predates the `seg-011` rewrite and is superseded. Rerun the follow-up set, with and without `--sin-historial`, and replace that table.

## Limits

- **The easy set is saturated.** A perfect score for every model means the questions are too easy to rank models. The harder set below addresses this.
- **Templated questions.** They are less varied than real user questions.
- **Single run per model.** No confidence intervals are computed.
- **Prices are partly unverified.** Gemini has no verified price, and OpenAI prices come from a third-party source.

## Status

- Week 7 reopened for one follow-up wording fix. Rerun pending.
- Easy set: 100 questions per language, validated, saturated.
- Harder set: 48 questions, 43 valid per language, results recorded.
- Context experiments: full schema, citations and the follow-up control, all recorded.
