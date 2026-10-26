# Actividad 7: GraphRAG (comparación acotada)

Corrida del 2026-10-26. Script: `experimentos/graphrag.py`. Modelo: claude-haiku-5-5.

## Grafo

Haiku extrajo entidades y relaciones de cada uno de los 57 chunks de semana 8 (fijo 400/80). El grafo se guardó en Postgres:
`semana9.entidades` (chunk, entidad, tipo) y `semana9.relaciones` (chunk, origen, relación, destino), con nombres normalizados (minúsculas, sin acentos).

- **Tamaño:** 426 entidades únicas y 532 relaciones.
- **Validez:** 57 de 57 extracciones con JSON válido (el script no carga el grafo si alguna falla). Caché: `grafo_extraccion.jsonl`.
- **Costo único de extracción:** 25,936 tokens de entrada y 90,017 de salida, **$0.0476**. Latencia p50 de 6.9 s por chunk. La salida es grande porque Haiku razona antes del JSON.
- **Entidades genéricas:** ninguna aparece en más del 30 % de los chunks (umbral fijado antes de correr), así que ninguna se excluyó de la expansión. La expansión pesa cada entidad por 1/df.

## Preguntas

Solo preguntas multi-salto, con dos pasajes de dos documentos distintos, congeladas antes del experimento:

- **compuestas** (`datasets/multisalto_*.jsonl`, 10 por idioma): la pregunta nombra ambos temas. Es el control.
- **puente** (`datasets/multisalto_puente_*.jsonl`, 10 por idioma): **el caso más favorable para GraphRAG**. La entidad que une los documentos no aparece en la pregunta. Por ejemplo, "¿cuántos días de tránsito hay desde Ciudad de México hasta el CEDIS que tiene capacidad para 12,000 posiciones de tarima?": hay que identificar Monterrey en un documento y buscar el tránsito en otro.

Validación: pasajes literales, completos dentro de un chunk y de documentos distintos (`datasets/construir_multisalto.py`).

## Métodos

- **V:** vectorial (bge-m3, OpenSearch `semana8`), top 10. Línea base.
- **V+R:** vectorial top 20 + reranking con Haiku, top 10. Es la comparación que pide el plan.
- **G:** 3 semillas vectoriales + chunks conectados por entidades compartidas o por una relación (peso 1/df), completando con el vectorial.
- **G+Q:** Haiku extrae las entidades de la pregunta, en español aunque la pregunta esté en inglés; los chunks que las mencionan se fusionan con el vectorial por RRF (k=60).

Métricas fijadas antes de correr: recall@5 sobre los dos pasajes, preguntas con ambos pasajes en el top 5, nDCG@10 y MRR, más costo y latencia por consulta.

## Resultados

| Set | Idioma | Método | recall@5 | Ambos pasajes en top 5 | nDCG@10 | MRR | Costo por consulta (USD) | Latencia p50 (ms) | Fallos |
|---|---|---|---|---|---|---|---|---|---|
| compuestas | es | V | 0.950 | 9/10 | 0.923 | 0.950 | 0 | 29 | 0 |
| compuestas | es | V+R | **1.000** | **10/10** | **1.000** | **1.000** | 0.000504 | 2281 | 0 |
| compuestas | es | G | **1.000** | **10/10** | 0.946 | 0.950 | 0 | 29 | 0 |
| compuestas | es | G+Q | 0.950 | 9/10 | 0.899 | 0.900 | 0.000137 | 1714 | 0 |
| compuestas | en | V | 0.850 | 7/10 | 0.845 | 0.870 | 0 | 26 | 0 |
| compuestas | en | V+R | **1.000** | **10/10** | **0.969** | **0.950** | 0.000502 | 2316 | 0 |
| compuestas | en | G | 0.850 | 8/10 | 0.830 | 0.867 | 0 | 26 | 0 |
| compuestas | en | G+Q | 0.950 | 9/10 | 0.901 | **0.950** | 0.000144 | 1685 | 0 |
| puente | es | V | 0.950 | 9/10 | 0.910 | **0.950** | 0 | 24 | 0 |
| puente | es | V+R | **1.000** | **10/10** | **0.941** | **0.950** | 0.000507 | 2585 | 0 |
| puente | es | G | 0.900 | 8/10 | 0.867 | **0.950** | 0 | 25 | 0 |
| puente | es | G+Q | **1.000** | **10/10** | 0.867 | 0.833 | 0.000150 | 1909 | 0 |
| puente | en | V | 0.750 | 5/10 | 0.778 | 0.875 | 0 | 25 | 0 |
| puente | en | V+R | **1.000** | **10/10** | **0.961** | **0.950** | 0.000490 | 2332 | 0 |
| puente | en | G | 0.800 | 6/10 | 0.766 | 0.875 | 0 | 25 | 0 |
| puente | en | G+Q | 0.850 | 7/10 | 0.805 | 0.925 | 0.000162 | 1822 | 0 |

Detalle por consulta: `graphrag_detalle.csv`.

## Lectura

- **Vector + reranking es el mejor método en los cuatro grupos.** Recupera ambos pasajes en el top 5 en 10 de 10 preguntas en cada set e idioma, y tiene el mejor nDCG@10. Cuesta unos $0.0005 por consulta y añade unos 2.3 s.
- **GraphRAG no supera esa línea base, ni siquiera en el caso más favorable (puente).** En puente EN, G+Q recupera 7 de 10 y V+R 10 de 10; en puente ES ambos llegan a 10 de 10, pero G+Q con peor orden (nDCG@10 0.867 frente a 0.941).
- **Por qué gana el reranking en este corpus:** V+R solo reordena los 20 primeros candidatos vectoriales y recuperó ambos pasajes en las 40 preguntas, así que en todas ambos pasajes estaban ya en el top 20 vectorial. Con 57 chunks, el top 20 es el 35 % del corpus. El problema del vectorial era ordenar el segundo pasaje, no encontrarlo, y eso lo resuelve un reranker.
- **G (expansión, sin costo en consulta)** mejora al vectorial en algunas preguntas (`ms-01`, `pt-05`), pero empeora en otras (`pt-08` y `pt-10` en ES): los vecinos del grafo desplazan resultados vectoriales que eran correctos. En neto empata o pierde, salvo en compuestas ES y puente EN.
- **G+Q (entidades de la pregunta)** ayuda sobre todo en inglés (compuestas EN de 7 a 9 de 10; puente EN de 5 a 7 de 10). Encontró entidades del grafo en 40 de 40 preguntas, incluidas las de inglés contra un grafo en español. Cuesta $0.00014 a $0.00016 por consulta, un tercio del reranking, pero recupera menos.
- **Costo total del grafo:** $0.048 de extracción una vez, más el costo por consulta de G+Q. Con un corpus de este tamaño no se recupera esa inversión.

## Conclusión

GraphRAG no aporta frente a la línea base de vector + reranking en este corpus, ni en preguntas compuestas ni en el caso más favorable, con la entidad puente oculta. No se adopta. Se documenta sin ajustar la métrica: las métricas, los umbrales (30 % de entidades genéricas, 3 semillas, RRF k=60) y los sets de preguntas se fijaron antes de correr.

El caso en que GraphRAG podría ganar es un corpus mucho mayor, donde el segundo pasaje quede fuera del top 20 vectorial y el reranker no pueda verlo. Ese caso no se probó aquí.

## Correcciones durante la actividad

- **Límite de tokens en la extracción:** con `max_tokens` 2000, 14 de 57 extracciones se cortaron en el límite, porque Haiku razona antes del JSON. El script se detuvo sin cargar el grafo, como estaba diseñado. Se subió a 6000; la salida más larga fue de 2,931 tokens. Las 43 extracciones válidas de la primera corrida se reutilizaron de la caché (su JSON estaba completo).
- **Servicios:** Postgres (`copilot-db`) y OpenSearch se detuvieron durante la sesión (apagado limpio, código 0) y se volvieron a levantar sin pérdida de datos.

## Limitaciones

- 10 preguntas por set e idioma: una pregunta mueve "ambos en top 5" un 10 %.
- Corpus pequeño (57 chunks): el top 20 cubre un tercio del corpus, lo que favorece al reranking.
- Grafo sin resolución de entidades más allá de la normalización: aparecen variantes como `cedis monterrey` y `cedis monterrey.md`.
- Una sola configuración de GraphRAG local (1 salto). No se probaron resúmenes de comunidades (GraphRAG global).
- LLM no determinista en extracción, reranking y entidades de la pregunta. Una corrida.
