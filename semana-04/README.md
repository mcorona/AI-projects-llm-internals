# Semana 4 · Inferencia: cuantización, latencia y costo

Práctica: benchmark del mismo conjunto de consultas en un modelo local cuantizado y en una API, midiendo latencia, throughput y costo.

## Estado

- [x] Script de benchmark (`benchmark_modelos.py`): latencia p50/p95, tokens por segundo y costo por 1 000 consultas.
- [x] Conjunto de 50 consultas (`consultas.jsonl`): 10 de código, 10 de redacción, 10 de razonamiento, 10 de negocio y 10 de explicación técnica. **Generado para esta práctica; no es el set de Cascada**, así que los resultados no son comparables con su benchmark.
- [x] Corrida local (Qwen3.8-27B en formato MLX, cuantizado a 4 bits, en LM Studio), 8192 tokens: `resultados/semana4_local_8k_*`.
- [x] Corrida API (Claude Haiku 5.5), 8192 tokens: `resultados/semana4_api_*`.
- [x] Destilación (práctica extra): entrenada y evaluada. 7B destilado con 37.0 % de coincidencia, igual que el 7B base. Sin ganancia. Ver `entrenamiento/README.md`.
- [x] DPO (práctica extra): no ejecutado. El CLI de `mlx-lm` instalado no tiene modo DPO. El dataset de 42 pares queda para un framework con soporte. Ver `entrenamiento/README.md`.

## Destinos

| Destino | Endpoint | Modelo | Precio (USD por millón) |
|---|---|---|---|
| Local | `http://localhost:1234/v1` (LM Studio) | `qwen3.8-27b-mlx@4bit` | 0 (la electricidad no se incluye) |
| API | `https://api.anthropic.com/v1/` (compatibilidad OpenAI de Anthropic) | `claude-haiku-5-5` | entrada 0.10, salida 0.50 |

Precio de Haiku 5.5 verificado en la [página oficial de precios de Anthropic](https://platform.claude.com/docs/en/about-claude/pricing): 0.10 USD por millón de tokens de entrada y 0.50 de salida hasta 100 000 tokens de prompt (octubre 2026). Si el precio cambia, ajusta `--precio-in` y `--precio-out`. Haiku 5.5 solo acepta `temperature` 1, por eso la API corre sin enviar temperatura (`--temp-api` vacío). El local usa temperatura 0.

## Resultados

Mismas 50 consultas, `--max-tokens 8192` en ambos destinos, temperatura 0 en el local y sin temperatura en la API.

| Métrica | Local: Qwen3.8-27B MLX 4 bits | API: Claude Haiku 5.5 |
|---|---|---|
| Latencia p50 | 52.4 s | 4.0 s |
| Latencia p95 | 137.6 s | 10.9 s |
| Latencia media | 53.0 s | 4.9 s |
| Tokens por segundo (mediana) | 23.4 | 185.0 |
| Costo por 1 000 consultas | 0 USD (electricidad no incluida) | 0.47 USD |
| Errores | 0 | 0 |

Lectura:

- La API es unas 13 veces más rápida en p50 y unas 12 veces en p95, y unas 8 veces en tokens por segundo.
- El local gasta más tokens por respuesta porque el 27B razona antes de contestar. Esos tokens de razonamiento cuentan en `tokens_salida`, así que el tiempo por respuesta visible sale distinto del que muestra la tabla.
- El costo local es cero en el script, pero la electricidad y el hardware no se contabilizan.

Limitaciones:

- **Este benchmark mide velocidad y costo, no calidad.** No se evaluó si las respuestas son correctas; eso ya se midió en la semana 3 con SQL.
- El set de 50 consultas es generado, no el de Cascada.
- Un solo intento por consulta; no hay repeticiones ni intervalos.

Corridas descartadas, se conservan para trazabilidad:

- `semana4_api` a 1024 tokens: 19 de 50 respuestas truncadas. Sustituida por la corrida de 8192.
- `semana4_local` a 1024 tokens: 27 de 50 respuestas truncadas. Sustituida por `semana4_local_8k`.

## Cómo correrlo

```bash
cd ~/AI-projects-llm-internals
read -s ANTHROPIC_API_KEY && export ANTHROPIC_API_KEY   # tu clave; no se escribe en el chat

# Local (LM Studio con el 27B cargado)
uv run python semana-04/benchmark_modelos.py --solo local \
  --local-modelo qwen3.8-27b-mlx@4bit --nombre semana4

# API (Haiku 5.5)
uv run python semana-04/benchmark_modelos.py --solo api \
  --api-url https://api.anthropic.com/v1/ --api-modelo claude-haiku-5-5 \
  --api-key-env ANTHROPIC_API_KEY --precio-in 0.10 --precio-out 0.50 --nombre semana4_api
```

Salidas: `resultados/<nombre>_detalle.csv` (una fila por consulta) y `resultados/<nombre>_resumen.json`.
Para correr los dos destinos en una sola ejecución, omite `--solo` y pasa también los parámetros del local.
