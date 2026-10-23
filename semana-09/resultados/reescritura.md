# Actividad 2: query rewriting con claude-haiku-5-5

Corrida del 2026-10-22. Vectorial de semana 8 (bge-m3, índice `semana8`, fijo 400/80). Script: `experimentos/reescritura.py`.
Métricas por consulta contra el pasaje de referencia; el top 10 se usa para nDCG@10 y MRR.

| Tipo | Idioma | Variante | recall@5 | nDCG@10 | MRR | Reescritura sin cambio | Costo por consulta (USD) | Latencia reescritura p50 / p95 (ms) |
|---|---|---|---|---|---|---|---|---|
| seguimiento | es | original | 0.933 | 0.809 | 0.747 | - | - | - |
| seguimiento | es | reescrita | 0.800 | 0.706 | 0.612 | 0/15 | 0.000040 | 917 / 1695 |
| base (control) | es | original | 1.000 | 0.904 | 0.874 | - | - | - |
| base (control) | es | reescrita | 0.980 | 0.898 | 0.867 | 49/50 | 0.000085 | 1353 / 2579 |
| seguimiento | en | original | 0.867 | 0.802 | 0.739 | - | - | - |
| seguimiento | en | reescrita | 1.000 | 0.798 | 0.732 | 0/15 | 0.000082 | 1424 / 2233 |
| base (control) | en | original | 1.000 | 0.885 | 0.845 | - | - | - |
| base (control) | en | reescrita | 1.000 | 0.885 | 0.845 | 49/50 | 0.000094 | 1545 / 2913 |

"Reescritura sin cambio" cuenta cuántas preguntas Haiku devolvió idénticas. En seguimiento es 0 por diseño, porque una pregunta de seguimiento siempre necesita reescribirse. En control, la reescritura debía dejar las preguntas autónomas como estaban.

## Lectura

- **Seguimiento en EN:** mejora recall@5 de 0.867 a 1.000 (dos preguntas más). nDCG@10 baja 0.004 y MRR baja 0.007, así que la mejora está en recall, no en orden.
- **Seguimiento en ES:** empeora recall@5 de 0.933 a 0.800 (dos preguntas menos). nDCG@10 y MRR también bajan. Es la señal contraria a EN, sin explicación todavía.
- **Control (base):** en ES, la reescritura cambió una pregunta autónoma y perdió una pregunta de recall (0.020). En EN no cambió nada. Cambiar una pregunta autónoma es un riesgo real, aunque sea pequeño.
- **Latencia:** la reescritura añade entre 0.9 y 1.5 s de mediana, y entre 1.7 y 2.9 s en p95. Es la latencia más alta de las técnicas que medimos hasta ahora.

## Conclusión

El resultado no alcanza para adoptar la reescritura como paso por defecto. En EN ayuda, en ES perjudica, y con 15 preguntas por idioma dos casos cambian el promedio. Se documenta como técnica con efecto dependiente del idioma. La decisión queda pendiente de dos cosas: identificar qué dos preguntas de seguimiento en ES perdieron recall, y verificar la anomalía de costo.

## Anomalía de costo

El costo por consulta del seguimiento en ES ($0.000040) es menor que el de la base en ES ($0.000085), aunque el seguimiento incluye la pregunta previa como contexto. No se explica con los datos de esta corrida. Antes de publicar la tabla de costos, hay que revisar los tokens de entrada y salida que devuelve la API para estas dos filas.

## Limitaciones

- 15 preguntas de seguimiento por idioma: un caso mueve el recall 0.067.
- Una sola corrida. Haiku no es determinista, así que las reescrituras pueden variar entre corridas.
- La línea base de seguimiento (sin reescritura) ya tiene recall alto (0.933 en ES y 0.867 en EN), así que hay poco margen para mejorar.
- La salida de importación de `chunking_pasajes.py` (tabla de chunking) aparece en la consola al correr el script. No forma parte de este experimento.
