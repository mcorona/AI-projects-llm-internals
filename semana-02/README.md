# Semana 2 · Tokens y variabilidad de la respuesta

Práctica de la Fase 1: cuántos tokens cuesta el mismo texto en español y en inglés, y cuánto varía la respuesta de un modelo según `temperature` y `top_p`.

## Archivos

- `entregable_semana2.ipynb`: entregable. Tabla de tokens por idioma y gráfica de variabilidad con las corridas guardadas.
- `texto_es.txt` y `texto_en.txt`: el mismo contenido (política de reorden de inventario) en español (231 palabras) e inglés (214 palabras).
- `practica_tokens.py`: cuenta tokens y calcula el costo por texto.
- `variabilidad.py`: genera N respuestas por condición en LM Studio y calcula la variabilidad (N por defecto = 20).
- `corridas/run1`, `run2`, `run3`: resultados de cada corrida de `variabilidad.py`.
- `resultados-n5/`: resultados preliminares con N = 5, antes de subir a 20.
- `logprobs_mlx.py` y `logprobs_temperaturas.py`: distribución de probabilidad del siguiente token, calculada con `mlx-lm`.
- `entropia_por_token.py` y `entropia_multisemilla.py`: entropía del siguiente token a lo largo de una respuesta.

---

## Parte 1 · Tokens por idioma

### Método

| Tokenizador | Tipo de conteo | Notas |
|---|---|---|
| tiktoken `o200k_base` | Exacto con ese tokenizador | Proxy abierto, no es el de Claude |
| Qwen2.5 (`Qwen/Qwen2.5-7B-Instruct`) | Exacto con su tokenizador | Qwen3 puede diferir; se declara como proxy de la familia |
| Claude `claude-sonnet-5-5` | Oficial, API `count_tokens` | Se restan 8 tokens de formato del mensaje (medidos con la letra "a") |

El costo usa la tarifa de entrada de `claude-sonnet-5-5`: **USD 2 por millón de tokens**, confirmada.

### Resultados

| Tokenizador | ES | EN | ES/EN | Extra en ES | Costo ES | Costo EN |
|---|---|---|---|---|---|---|
| tiktoken (proxy) | 280 | 246 | 1.14 | 14% | — | — |
| Qwen2.5 | 321 | 246 | 1.30 | 30% | — | — |
| **Claude (oficial)** | **503** | **371** | **1.36** | **36%** | **$0.001006** | **$0.000742** |

### Conclusiones

- En Claude, el mismo contenido en español cuesta 36% más tokens que en inglés.
- El proxy abierto (tiktoken) subestima ese sobrecosto: 14% frente a 36%. Un presupuesto hecho con un tokenizador abierto queda unos 20 puntos por debajo del costo real en español.
- Qwen también es menos eficiente en español que tiktoken (30%).
- El costo por texto es pequeño, pero escala con el volumen. Para propuestas, usa el conteo oficial de Claude y declara que los otros son estimaciones.

### Limitaciones

- Las traducciones tienen longitud distinta (231 frente a 214 palabras), así que parte del sobrecosto refleja la longitud del texto y no solo el tokenizador. Para aislarlo, habría que medir por caracteres o por contenido equivalente.
- Es un solo texto de muestra. Conviene repetir con otros tipos de documento (técnico, legal, conversacional).
- El conteo oficial incluye 8 tokens de formato fijos, que se restan en la tabla.

---

## Parte 2 · Variabilidad de la respuesta

### Método

- Modelo: `qwen3.8-27b-mlx@4bit` en LM Studio (local).
- Prompt: "Explica en tres frases qué es el punto de reorden de un SKU y cuándo conviene revisarlo."
- Por condición se piden 20 respuestas. La variabilidad de cada respuesta es 1 − su similitud Jaccard promedio contra las demás (sobre palabras en minúscula). 0 significa que todas son idénticas.
- Barrido de `temperature` con `top_p` = 1.0, y de `top_p` con `temperature` = 1.0.
- Se hicieron **3 corridas** (60 respuestas por condición). El intervalo de confianza es 95 % aproximado (normal) sobre las 60 cifras.

### Resultados

| Condición | Corrida 1 | Corrida 2 | Corrida 3 | Promedio | IC 95 % |
|---|---|---|---|---|---|
| temperature 0.0 | 0.150 | 0.000 | 0.000 | 0.050 | [0.024, 0.076] |
| temperature 0.7 | 0.665 | 0.603 | 0.600 | 0.623 | [0.608, 0.637] |
| temperature 1.0 | 0.695 | 0.700 | 0.725 | 0.707 | [0.685, 0.729] |
| top_p 0.5 | 0.536 | 0.526 | 0.539 | 0.534 | [0.527, 0.540] |
| top_p 0.9 | 0.657 | 0.647 | 0.677 | 0.661 | [0.643, 0.678] |
| top_p 1.0 | 0.657 | 0.693 | 0.657 | 0.669 | [0.654, 0.684] |

### Conclusiones

- **Temperature:** de 0.7 a 1.0 la variabilidad sube de forma clara; los intervalos no se traslapan.
- **Top_p:** con 0.5 la variabilidad es claramente menor. Entre 0.9 y 1.0 los intervalos se traslapan, así que este experimento no permite afirmar que sean distintos.
- **Temperature 0.0** no siempre da cero: en la corrida 1 dio 0.150. La causa no está identificada; podría ser no determinismo del runtime en esa ejecución.

### Limitaciones

- Jaccard mide variación de palabras, no de significado. Dos respuestas con el mismo contenido y distinta redacción puntúan como diferentes.
- Un solo prompt y un solo modelo local. No se generalizan a otros modelos ni prompts sin repetir el experimento.
- Los modelos de Claude (Sonnet 5.5, Opus 5.5, Fable 5.1) no aceptan `temperature` libre; Haiku 5.5 solo acepta `temperature` = 1 y `top_p` = 0.99. Por eso el barrido se hizo con Qwen local.
- Las 60 cifras por condición no son independientes, porque comparten respuestas dentro de cada corrida. Los intervalos son algo optimistas.
- La diferencia entre `top_p` 0.9 y 1.0 no se resuelve con 3 corridas.

---

## Probabilidades por token

### Qué expone cada API

- **Anthropic (Messages API):** no expone logprobs. La referencia de `Create a Message` no tiene parámetros ni campos de probabilidad.
- **LM Studio (`/v1/chat/completions`):** acepta `logprobs` pero devuelve `null`. No hay probabilidades por token desde la API.

Por eso las probabilidades se calcularon localmente con `mlx-lm` sobre el mismo modelo.

### Distribución del primer token

Prompt "Di hola", con `enable_thinking=False`:

| T | Entropía (bits) | p(`¡`) |
|---|---|---|
| 0.0 | 0.000 | 1.0000 |
| 0.7 | 0.147 | 0.9826 |
| 1.0 | 0.612 | 0.9209 |

El primer token casi no varía. Con `top_p` = 0.9, el núcleo es un solo token en las tres temperaturas.

### Entropía a lo largo de la respuesta

Con 20 semillas por temperatura (`entropia_multisemilla.py`), la entropía media por respuesta es:

| T | Entropía media (bits) | IC 95 % | Respuestas distintas |
|---|---|---|---|
| 0.7 | 0.518 | [0.502, 0.534] | 20/20 |
| 1.0 | 0.954 | [0.898, 1.010] | 20/20 |

La incertidumbre se concentra en la redacción (sinónimos válidos como "asegurar" o "garantizar"), no en el significado. Eso explica en parte por qué Jaccard mide variación léxica y no de contenido.

---

## Cómo correrlo

```bash
cd ~/AI-projects-llm-internals

# Tokens y entregable
uv run --with jupyter jupyter lab semana-02/entregable_semana2.ipynb

# Variabilidad (LM Studio encendido con qwen3.8-27b-mlx@4bit)
uv run python semana-02/variabilidad.py 20

# Entropía por semilla
uv run python semana-02/entropia_multisemilla.py 20
```

Para el conteo de tokens desde script: `uv run python semana-02/practica_tokens.py`. Necesita `ANTHROPIC_API_KEY` en el entorno para el conteo oficial de Claude.
