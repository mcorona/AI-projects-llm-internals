# AI-projects-llm-internals

Laboratorio de la Fase 1 del programa "Experto en GenAI para Negocios Internacionales": fundamentos de LLMs, construidos desde cero siguiendo la serie Zero to Hero de Andrej Karpathy, en MLX (Apple Silicon).

## Estructura

| Carpeta / archivo | Contenido |
|---|---|
| `semana-01/` | Bigram (PyTorch y MLX), atención causal, mini-GPT, entrenamiento y práctica de memoria del KV cache |
| `semana-01/README.md` | Notas de la semana: resultados, glosario y decisiones |

## Requisitos

- macOS con Apple Silicon.
- [uv](https://docs.astral.sh/uv/) y Python 3.13.

## Cómo correr la semana 1

```bash
uv sync
cd semana-01
./get_data.sh
uv run python bigram_mlx.py
uv run python attention_mlx.py
uv run python minigpt_mlx.py
uv run python train_minigpt_mlx.py
uv run python practica_kv_cache.py
```

## Criterio de salida de la Fase 2

Cada semana de la Fase 2 se cierra solo si cumple lo siguiente:

- [x] Los prompts y las evals viven en Git con versión (`semana-05/prompts/`, `semana-06/golden/`).
- [x] Hay una eval automática de regresión (`semana-06/evaluar.py`) que corre en GitHub Actions cuando cambian prompts, evals o `semana-07/`.
- [x] Los cambios de prompt o modelo entran por pull request, no por push directo a `main`, con la protección de rama `ProteccionRama` y el check `regresion` como requisito (verificado con el PR #2).
- [x] La eval de NLQ (semana 7) corre en cada PR, con Haiku sobre el set difícil y una base de CI con datos sintéticos de semilla 42. Verificada en el PR #3 (exactitud 0.953 en español y 1.000 en inglés); umbral 0.90 desde el PR siguiente.
- [x] Cada semana publica sus resultados en su README, con costo y exactitud por modelo.

Lo que no cumple el criterio queda marcado como pendiente hasta que se resuelva.

## Criterio de salida de la Fase 3

La Fase 3 cubre las semanas 8, 9 y 10 (recuperación y RAG avanzado). Solo se marca lo verificado con evidencia en el repo.

- [x] La eval de recuperación corre en CI en cada PR que toca `semana-08/**` o `semana-09/**`, con umbral de recall@5 por idioma (0.90), calibrado con la primera corrida (ES 0.990, EN 0.950). Verificado en los PR #15 y #17 para semana 8 (`semana-08/resultados/ci_recuperacion.md`) y en el PR #29 para semana 9 (`semana-09/resultados/ci_semana09.md`).
- [x] Hay una comparación documentada de chunking, embeddings y bases vectoriales con recall@k, latencia y costo, en ES y EN (`semana-08/README.md`, actividades 2 a 5; chunking en `semana-08/resultados/chunking.md`, registrado el 2026-10-26).
- [x] La búsqueda híbrida y el reranking se miden contra la línea base. Reranking: nDCG@10 ES 0.904 → 0.982, EN 0.885 → 0.974. Híbrida (BM25 + vectorial con RRF): no mejora recall@5 (ES 1.000 → 0.970, EN 1.000 → 0.770) y no se adopta (`semana-08/resultados/hibrida.md`).
- [x] Las respuestas con citas se evalúan con juez, con exactitud y precisión de citas reportadas (`semana-08/README.md`, actividad 8).
- [x] Las técnicas avanzadas (reescritura, HyDE y contextual retrieval) se miden con el mismo golden set congelado, y se adoptan solo si mejoran. Las tres están medidas; ninguna mejora a la línea base y ninguna se adopta (`semana-09/resultados/comparacion_final.md`; PR #19, #20, #21 y #23).
- [x] Los filtros por tenant y roles se aplican dentro de la consulta en pgvector, Qdrant y OpenSearch, con fuga de permisos igual a 0 y prueba cruzada entre tenants. Criterio no negociable. Verificado con fuga 0 en las tres bases (PR #25 y #26) y con un check de CI que falla ante cualquier fuga en cada PR de semana 9 (PR #29).

Lo que no cumple el criterio queda marcado como pendiente hasta que se resuelva.

## Estado

- Semana 1: completa. Mini-GPT de 2000 pasos con pérdida de validación de 1.72 (n=128, lr=1e-3). Ver `semana-01/README.md`.
