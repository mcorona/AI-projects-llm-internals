# Week 11: RAG evaluation (recall@k, faithfulness, answer relevance with RAGAS; cost per query)

Status: in progress.

Goal: evaluate retrieval and generation with separate suites, so a regression can be traced to the stage that caused it, and check that each metric detects known failures before relying on it.

## Setup

- RAGAS installed in the repo `.venv`; exact versions are recorded by `experimentos/verificar_ragas.py`.
  - The current `ragas` release imports `langchain_community.chat_models.vertexai`, which the latest `langchain-community` removed. Pin `langchain-community==0.4.1`.
  - The judge is Claude through `llm_factory(..., provider="anthropic")`. RAGAS sends `temperature` and `top_p` by default; both are removed because current Claude models do not accept the pair.
  - Embeddings use bge-m3 in LM Studio through its OpenAI-compatible endpoint.
- Index: `semana10.chunks` from week 10, activity 7 (30 documents, 68 chunks, tenant `alfa`). Check it with `experimentos/verificar_entorno.py`.
