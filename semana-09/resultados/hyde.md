# Actividad 3: HyDE con claude-haiku-5-5

Vectorial de semana 8 (bge-m3, índice `semana8`, fijo 400/80). Script: `experimentos/hyde.py`.
Haiku escribe un pasaje hipotético; ese pasaje se embebe y busca en lugar de la pregunta original.
Base: pregunta autónoma. Seguimiento: el pasaje se genera con la pregunta previa como contexto.
Permisos fuera de esta métrica (se evalúan en la actividad 5).

## Corrida válida (max_tokens 1500)

Chequeo de respaldo: 0 de 130 pasajes iguales a la pregunta. Detalle: `hyde_detalle.csv`.

| Tipo | Idioma | Variante | recall@5 | nDCG@10 | MRR | Costo por consulta (USD) | Latencia HyDE p50 / p95 (ms) |
|---|---|---|---|---|---|---|---|
| base | es | original | 1.000 | 0.904 | 0.874 | - | - |
| base | es | HyDE | 0.960 | 0.886 | 0.856 | 0.000098 | 1375 / 3129 |
| seguimiento | es | original | 0.933 | 0.809 | 0.747 | - | - |
| seguimiento | es | HyDE | 0.933 | 0.750 | 0.668 | 0.000097 | 1405 / 2688 |
| base | en | original | 1.000 | 0.885 | 0.845 | - | - |
| base | en | HyDE | 0.880 | 0.816 | 0.772 | 0.000137 | 1914 / 3184 |
| seguimiento | en | original | 0.867 | 0.802 | 0.739 | - | - |
| seguimiento | en | HyDE | 0.933 | 0.774 | 0.702 | 0.000159 | 2165 / 3091 |

## Primera corrida (max_tokens 250, descartada como medición)

Cinco de 130 respuestas tenían solo el bloque de razonamiento y sin texto; el script usó la pregunta original como pasaje. Además, la mayoría de las salidas quedaron cerca del límite y probablemente se truncaron. Se corrigió el límite a 1500 y se volvió a correr. El CSV de esa corrida se conserva como `hyde_detalle_corrida1.csv` en la carpeta local, no en el repo.

## Lectura

- **No mejora ninguna métrica de ranking.** nDCG@10 y MRR bajan en las cuatro celdas, salvo base ES, donde nDCG sube 0.018 con una pregunta menos recuperada.
- **Recall:** base cae en ES (una pregunta menos) y en EN (seis preguntas menos). Seguimiento EN sube una pregunta; seguimiento ES no cambia.
- **Costo:** $0.000097 a $0.000159 por consulta, unas dos veces el costo de la reescritura por la salida de texto más larga.
- **Latencia:** p50 entre 1.4 y 2.2 s, con p95 de hasta 3.6 s. Es la técnica más lenta de las probadas hasta ahora, y no aporta ganancia.

Los tipos de bloque confirman lo que se vio en la reescritura: Haiku devuelve bloques `thinking` además de `text`, y esos tokens se cobran como salida.

## Conclusión

HyDE no mejora el recall ni el ranking en este golden set. Se documenta como técnica que no aporta. No se adopta por defecto, ni para base ni para seguimiento. La diferencia en recall de EN base (seis preguntas) es la señal más clara en contra.

## Limitaciones

- Una corrida válida. La variabilidad de Haiku observada en la reescritura sugiere que las diferencias de una o dos preguntas pueden ser ruido.
- Un solo modelo de generación (Haiku) y un solo tamaño de pasaje hipotético.
- Los casos de permiso no entran en esta métrica.
