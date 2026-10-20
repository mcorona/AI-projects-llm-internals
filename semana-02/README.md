# Semana 2 · Tokens: español frente a inglés

Práctica de la Fase 1: cuántos tokens cuesta el mismo texto en español y en inglés, con tres tokenizadores.

## Archivos

- `texto_es.txt` y `texto_en.txt`: el mismo contenido (política de reorden de inventario) en español (231 palabras) e inglés (214 palabras).
- `practica_tokens.py`: cuenta tokens y calcula el costo por texto.

## Método

| Tokenizador | Tipo de conteo | Notas |
|---|---|---|
| tiktoken `o200k_base` | Exacto con ese tokenizador | Proxy abierto, no es el de Claude |
| Qwen2.5 (`Qwen/Qwen2.5-7B-Instruct`) | Exacto con su tokenizador | Qwen3 puede diferir; se declara como proxy de la familia |
| Claude `claude-sonnet-5-5` | Oficial, API `count_tokens` | Se restan 8 tokens de formato del mensaje (medidos con la letra "a") |

El costo usa la tarifa de entrada de `claude-sonnet-5-5`: **USD 2 por millón de tokens**, confirmada.

## Resultados

| Tokenizador | ES | EN | ES/EN | Extra en ES | Costo ES | Costo EN |
|---|---|---|---|---|---|---|
| tiktoken (proxy) | 280 | 246 | 1.14 | 14% | — | — |
| Qwen2.5 | 321 | 246 | 1.30 | 30% | — | — |
| **Claude (oficial)** | **503** | **371** | **1.36** | **36%** | **$0.001006** | **$0.000742** |

## Conclusiones

- En Claude, el mismo contenido en español cuesta 36% más tokens que en inglés.
- El proxy abierto (tiktoken) subestima ese sobrecosto: 14% frente a 36%. Un presupuesto hecho con un tokenizador abierto queda unos 20 puntos por debajo del costo real en español.
- Qwen también es menos eficiente en español que tiktoken (30%).
- El costo por texto es pequeño, pero escala con el volumen. Para propuestas, usa el conteo oficial de Claude y declara que los otros son estimaciones.

## Limitaciones

- Las traducciones tienen longitud distinta (231 frente a 214 palabras), así que parte del sobrecosto refleja la longitud del texto y no solo el tokenizador. Para aislarlo, habría que medir por caracteres o por contenido equivalente.
- Es un solo texto de muestra. Conviene repetir con otros tipos de documento (técnico, legal, conversacional).
- El conteo oficial incluye 8 tokens de formato fijos, que se restan en la tabla.

## Cómo correrlo

```bash
cd ~/AI-projects-llm-internals/semana-02
export ANTHROPIC_API_KEY=...   # o carga tu archivo de configuración
uv run python practica_tokens.py
```
