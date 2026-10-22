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
- [ ] La eval de NLQ (semana 7) corre en cada PR, con Haiku sobre el set difícil y una base de CI con datos sintéticos de semilla 42. Pendiente de verificar en un PR; umbral provisional de 0.80.
- [x] Cada semana publica sus resultados en su README, con costo y exactitud por modelo.

Lo que no cumple el criterio queda marcado como pendiente hasta que se resuelva.

## Estado

- Semana 1: completa. Mini-GPT de 2000 pasos con pérdida de validación de 1.72 (n=128, lr=1e-3). Ver `semana-01/README.md`.
