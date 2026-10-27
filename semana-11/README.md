# Week 11: RAG evaluation (recall@k, faithfulness, answer relevance with RAGAS; cost per query)

Status: in progress.

Goal: evaluate retrieval and generation with separate suites, so a regression can be traced to the stage that caused it, and check that each metric detects known failures before relying on it.

## Setup

- RAGAS installed in the repo `.venv` with `uv pip install "ragas==0.4.3" "langchain-community==0.4.1" anthropic`. Versions recorded on 2026-10-27: ragas 0.4.3, langchain-community 0.4.1, langchain-core 1.7.0, instructor 1.17.0, anthropic 1.15.0, openai 3.3.0.
  - The current `ragas` release imports `langchain_community.chat_models.vertexai`, which the latest `langchain-community` removed. Pin `langchain-community==0.4.1`.
  - The judge is Claude through `llm_factory(..., provider="anthropic")`. RAGAS sends `temperature` and `top_p` by default; both are removed because current Claude models do not accept the pair.
  - Embeddings use bge-m3 in LM Studio through its OpenAI-compatible endpoint.
- Index: `semana10.chunks` from week 10, activity 7 (30 documents, 68 chunks, tenant `alfa`). Check it with `experimentos/verificar_entorno.py`.

## Setup check (2026-10-27)

`experimentos/verificar_ragas.py`, judge Haiku 5.5 `low`, embeddings bge-m3. Four cases with a known outcome, built from a verbatim passage of `semana-08/corpus/devoluciones.md`:

| Case | faithfulness | answer_relevancy | context_recall |
|---|---|---|---|
| Faithful answer | 1.00 | 0.94 | 1.00 |
| Changed figure (45 instead of 30 days) | **0.00** | 0.74 | 1.00 |
| True but off-topic answer | 1.00 | **0.58** | 1.00 |
| Wrong context, answer says "not in context" | 0.00 | 0.00 | **0.00** |

Every metric moved in the expected direction. Cost: 24 judge calls, 39,090 input and 2,454 output tokens, $0.0051.

Two readings to carry into activity 3:
- A correct abstention ("not in the context") scores faithfulness 0 and answer relevance 0: RAGAS finds no supported claim and treats the answer as noncommittal. Unanswerable questions need their own metric (abstention rate), not RAGAS.
- answer_relevancy also dropped for the changed figure (0.94 → 0.74), so it is not purely a topic measure.

`experimentos/verificar_entorno.py`: LM Studio serves `text-embedding-bge-m3` (1024 dimensions). `semana10.chunks` had been left by the week 10 security run (alfa 36 documents, 79 chunks; beta 10, 33; six injected documents). It was reindexed to the activity 7 index: 30 documents, 68 chunks, tenant `alfa` only.

## 1. Evaluation gold set (frozen)

`datasets/eval_rag_{es,en}.jsonl`, built by `datasets/construir_eval_rag.py`. 75 questions per language:

| Type | Per language | `gold` | `referencia` |
|---|---|---|---|
| Base (weeks 8/9) | 50 | Verbatim passages | Written by Haiku 5.5 `low` from the passage only, with the source document to interpret it (for example, a table header) |
| Non-text (week 10: 5 PDF, 5 OCR, 5 image) | 15 | Source document and exact answer | Same, with the source document and the exact answer |
| Unanswerable | 10 | empty | "The information is not in the documents." |

The 15 week 10 document questions come from the same 50 base questions (field `origen`), so they are not added twice. The unanswerable questions stay in the domain (vacation days, cargo insurer, accounting software, late-payment interest, CEO, remote work, year-end bonus, uniforms, factoring, carrier strike); the builder checks that their key terms do not appear in the week 8 corpus or the week 10 sources.

Automatic checks, all passing: every figure in a reference appears in the passage (or the document line that contains it), the source or the question; non-text references contain the exact answer; no answerable question has a reference that says the answer is missing.

| Run | What happened | Cost |
|---|---|---|
| v1 (passage only) | Two references said the answer was missing: `rec-07` read a table row without its header as a salary range, and `rec-23` EN did not see that the passage is the escalation threshold. The figure check also flagged 5 figures that came from the question | $0.0073 |
| v2 (passage + source document for context) | All checks pass; v1 answers are kept in the cache as evidence | $0.0117 |

Manual review of 20 references (10 per language, seed 11): **20/20 correct**; two add a detail from the same source line, verified ([`revision_referencias.md`](resultados/revision_referencias.md)).
