# Semana 6: evals y regresión en GitHub Actions

Objetivo: cualquier cambio de prompt o de modelo se mide antes de fusionarse. El evaluador corre los casos dorados, aplica checks deterministas y un juez LLM para la fidelidad de los resúmenes, y compara contra una línea base.

## Estructura

| Archivo | Contenido |
|---|---|
| `evaluar.py` | Evaluador: genera la salida con las plantillas de `semana-05`, aplica checks y compara con la línea base |
| `golden/casos.jsonl` | 16 casos dorados (6 clasificación, 4 extracción, 3 herramienta, 3 resumen). Borrador de autor, pendiente de revisión |
| `rubricas/fidelidad_resumen.txt` | Rúbrica del juez: escala de 1 a 5 y salida en JSON |
| `baseline/resultados_base.json` | Línea base contra la que se compara (se genera con `--actualizar-base`) |
| `resultados/` | Reporte de cada corrida (`eval_<fecha>.json`) |
| `../.github/workflows/evals-semana-06.yml` | Workflow que corre las evals en cada pull request que toque prompts, el ejecutor o esta carpeta |

## Checks

- `etiqueta`: la salida es exactamente la etiqueta esperada.
- `json_campos`: la salida es JSON válido y los campos indicados coinciden (`null` cuenta como coincidencia).
- `herramienta`: el modelo llamó `buscar_sku` con la entrada esperada, o no llamó ninguna herramienta cuando el caso lo pide.
- `resumen_estructura`: tres viñetas de máximo 25 palabras, o `INSUFICIENTE`.
- `juez: true`: además del check estructural, el juez puntúa la fidelidad del resumen al documento. El caso pasa con fidelidad de 4 o 5.

## Regresión

El evaluador falla (código 1) si ocurre cualquiera de estas dos cosas frente a la línea base:

- Un caso que antes pasaba ahora falla.
- La tasa de aprobación cae más de 0.05.

## Cómo correr

```bash
cd ~/AI-projects-llm-internals
python3 semana-06/evaluar.py                      # compara con la línea base si existe
python3 semana-06/evaluar.py --actualizar-base    # guarda esta corrida como línea base
python3 semana-06/evaluar.py --limite 3           # prueba rápida con 3 casos
```

La clave se lee de `ANTHROPIC_API_KEY` en el entorno o de `semana-05/.env`. En GitHub Actions se toma del secreto del repositorio.

## Decisiones

- **El juez es el mismo modelo que genera** (`claude-haiku-5-5`). Es una limitación conocida: un juez de la misma familia puede favorecer sus propias salidas. Más adelante conviene probar un juez de otra familia.
- **Las herramientas se evalúan por nombre y entrada**, no por el texto de la respuesta, porque en esos casos el modelo no escribe texto.
- **La línea base se versiona en Git.** Si se actualiza, debe quedar en el mismo commit que el cambio que la justifica.
- **Los casos dorados son un borrador de autor.** Antes de usarlos como referencia, hay que revisar cada caso con el equipo.

## Estado

- Evaluador y casos: creados. Checks deterministas probados sin llamadas a la API (10 de 10 casos de prueba correctos tras corregir un error de índice en la prueba).
- Línea base: pendiente. Se genera con una corrida real (`--actualizar-base`) y se commitea.
- Secreto `ANTHROPIC_API_KEY` en GitHub: pendiente de configurar en Settings → Secrets and variables → Actions.
- Juez de otra familia: pendiente, para la siguiente iteración.

Prueba del workflow: 2026-10-21
