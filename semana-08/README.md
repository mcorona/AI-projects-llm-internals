# Week 8: retrieval (chunking, embeddings, vector DBs, BM25 + reranking, cited answers, CI)

Goal: measure which retrieval choices work for a small, bilingual document base, using the same
gold passages for every experiment. The gold set was written by the author, so it may favor the
author's wording. Results are a first measurement, not a verdict.

## Corpus and gold set

- 24 markdown documents of a fictional company: 9 copied unchanged from `inventory-copilot/data/docs`
  and 15 written for this week (`corpus/`).
- `datasets/recuperacion_es.jsonl` and `datasets/recuperacion_en.jsonl`: 50 questions per language.
  The EN questions are translations of the ES ones with the same gold passages, so EN queries against
  the Spanish corpus test cross-lingual retrieval.
- A gold passage is an exact sentence from a document. A chunk counts as a hit when it contains the
  passage verbatim. This keeps the metric independent of how the text is split.
- All gold passages were checked to appear verbatim in their source documents.

## 1 and 2: chunking

Chosen default: fixed window of 400 characters with 80 overlap (57 chunks). It was compared against a
recursive splitter (paragraph and sentence packing) and the section-based chunker from inventory-copilot
(`experimentos/chunker_actual.py`). The per-strategy recall numbers were not saved to a results file in
the repo, so they are not reported here. Re-run `experimentos/recall_chunking.py` to reproduce them.

Reason for the default: it had the best recall in the first comparison and keeps the code and the
pipeline simple. Its known weakness is that it ignores section boundaries, so citations can be less precise.

## 3: embedding models

Fixed window 400/80, 57 chunks, 50 queries per language. Source: `resultados/embeddings_fijo_400_solape_80.md`.

| Model | Dimension | ES recall@5 | ES recall@10 | EN recall@5 | EN recall@10 | Cost (USD) |
|---|---|---|---|---|---|---|
| bge-m3 (local, LM Studio) | 1024 | 1.000 | 1.000 | 1.000 | 1.000 | 0 |
| text-embedding-3-small | 1536 | 0.990 | 1.000 | 0.950 | 0.980 | 0.000129 (ES) / 0.000124 (EN) |
| text-embedding-3-large | 3072 | 1.000 | 1.000 | 1.000 | 1.000 | 0.000841 (ES) / 0.000809 (EN) |
| gemini-embedding-2 | 3072 | 0.980 | 1.000 | 0.980 | 1.000 | pending (see limits) |

OpenAI prices: https://developers.openai.com/api/docs/models (checked 2026-10-22).
Gemini: $0.20 per million input tokens, the figure the author provided. The source URL and the token count are pending.

bge-m3 was chosen: no API cost, and its 1024 dimensions match the `doc_chunks.embedding` column in
inventory-copilot. The top two tied at 1.000 on this set, and the differences elsewhere are one or two
passages out of 50, so they are not conclusive by themselves.

## 4 and 5: vector databases

Same vectors (bge-m3, fixed 400/80) in pgvector, Qdrant and OpenSearch. Script: `experimentos/medir_vector_dbs.py`.

| Engine | Index | recall@5 | recall@10 | p50 ms | p95 ms | Index size |
|---|---|---|---|---|---|---|
| pgvector | HNSW, `vector_cosine_ops` | 1.000 | 1.000 | 1.0 | 1.4 | 880 kB |
| Qdrant v1.12.4 | HNSW, cosine | 1.000 | 1.000 | 2.2 | 2.8 | not reported |
| OpenSearch 2.19.1 | knn_vector, lucene HNSW, cosinesimil | 1.000 | 1.000 | 6.2 | 7.6 | 1.4 MB |

Metadata filter (`source = politica_reorden.md`): 5 of 5 correct in all three.

Limits:
- Latency is not like-for-like. pgvector runs inside Postgres; Qdrant and OpenSearch are HTTP calls, so part of their latency is network and JSON.
- Index parameters are the engine defaults. Nothing was tuned.
- The first OpenSearch filter run returned 1 of 5 because the filter was applied after the k-NN search. Moving it inside the knn clause fixed it.

## 6: BM25 and hybrid search

`experimentos/hibrida_bm25.py` implements BM25 (OpenSearch `match` on `content`), vector search, and
RRF fusion (k = 60, top 20 from each list). The numbers were not saved to a results file, so they are
not reported here. Re-run the script to reproduce them.

The gold set has no exact-term queries (codes, IDs, SKUs). That is the case where BM25 is expected to
help most, so the hybrid result on this set does not show whether hybrid search is worth it in general.

## 7: reranking with claude-haiku-5-5

Reranker applied to the top 20 vector candidates. Script: `experimentos/reranking.py`.

| Language | Method | nDCG@10 | MRR |
|---|---|---|---|
| ES | Vector | 0.904 | 0.874 |
| ES | Vector + Haiku rerank | 0.982 | 0.980 |
| EN | Vector | 0.885 | 0.845 |
| EN | Vector + Haiku rerank | 0.974 | 0.967 |

Metric notes: nDCG uses binary relevance, and each gold passage counts once, because overlapping chunks
can contain the same passage. An earlier version counted duplicates and produced nDCG above 1; it was fixed.

Extra cost and latency: about $0.0005 per query, p50 about 2.4 s per query.
LLM outputs are not deterministic, so each figure comes from one run.

## 8: cited answers and evaluation

Top 5 chunks after reranking. Haiku answers with citations [n]. Haiku judges the answer against the gold passage.
Script: `experimentos/end_to_end.py`.

| Language | Correct answers (judge) | Citation precision | Cost per answer |
|---|---|---|---|
| ES | 1.000 | 0.768 | $0.000683 |
| EN | 0.980 | 0.853 | $0.000706 |

Citation precision counts a citation as correct only if the cited chunk contains a gold passage. A citation
can point to a chunk that answers the question without containing that exact passage, and the metric counts
it as wrong. Treat it as a proxy. The judge is also a model, so its verdicts are not ground truth.

## 9: retrieval eval in CI

Workflow `.github/workflows/recuperacion-semana-08.yml` runs on every PR that touches `semana-08/**`.
It uses a `pgvector/pgvector:pg16` service and `text-embedding-3-small` (`ci/recuperacion_ci.py`), because
bge-m3 runs in LM Studio, which GitHub Actions cannot reach. Threshold: recall@5 >= 0.90 per language.
The OpenAI key is the repository secret `OPENAI_API_KEY`. The check passed on the PR for this week. First CI run: recall@5 ES 0.990, EN 0.950 (threshold kept at 0.90; see `resultados/ci_recuperacion.md`).

## Limits

- Small corpus (24 documents, 57 chunks) and 50 questions per language: one or two questions change a ranking.
- The author wrote the gold set and the questions. This can favor the author's wording.
- EN questions against a Spanish corpus test cross-lingual retrieval, not a native English corpus.
- LLM steps (reranker, answerer, judge) are not deterministic. Most figures come from one run.
- Citation precision and the judge are proxies based on passage matching.
- Hybrid search was not tested on exact-term queries, so its best case is not measured here.
- Gemini embedding price comes from the author; the source URL and the token count are pending.
- CI uses OpenAI embeddings, not the local bge-m3 model used in the measurements.
- Docker services are for local development: single node, security plugin disabled.
- The root README has no Phase 3 exit criteria yet, so this week is not checked against them.

## Status

Activities 1 to 9 are done. This README is activity 10.
