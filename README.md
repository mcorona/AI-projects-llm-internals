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

## Estado

- Semana 1: completa. Mini-GPT de 2000 pasos con pérdida de validación de 1.72 (n=128, lr=1e-3). Ver `semana-01/README.md`.
