# Actividad 4: contextual retrieval con claude-haiku-5-5

Corrida del 2026-10-26. Script: `experimentos/contextual.py`.
Para cada uno de los 57 chunks de semana 8 (fijo 400/80), Haiku recibe el documento completo y el chunk, y escribe un contexto breve.
El embedding (bge-m3) se calcula sobre `contexto + chunk` y se indexa en OpenSearch como `semana9_ctx`.
El campo `content` guarda el chunk original, así que la comparación contra el pasaje de referencia es idéntica a la de la línea base (`semana8`).
Las consultas son las mismas en ambos índices. Los casos de permiso se evalúan en la actividad 5.

Validez: 57 de 57 contextos con texto (el script no indexa si alguno sale vacío). Todas las respuestas fueron solo bloque `text`.
Contextos: `contextos.jsonl`. Detalle por consulta: `contextual_detalle.csv`.

## Resultados

| Tipo | Idioma | Índice | recall@5 | nDCG@10 | MRR |
|---|---|---|---|---|---|
| base | es | semana8 (línea base) | 1.000 | 0.904 | 0.874 |
| base | es | semana9_ctx | 0.970 | 0.873 | 0.834 |
| seguimiento | es | semana8 (línea base) | 0.933 | 0.809 | 0.747 |
| seguimiento | es | semana9_ctx | 0.933 | 0.805 | 0.763 |
| base | en | semana8 (línea base) | 1.000 | 0.885 | 0.845 |
| base | en | semana9_ctx | 0.970 | 0.875 | 0.841 |
| seguimiento | en | semana8 (línea base) | 0.867 | 0.802 | 0.739 |
| seguimiento | en | semana9_ctx | 0.800 | 0.798 | 0.756 |

## Costo y tamaño

- **Indexado (una sola vez):** 42,119 tokens de entrada y 6,111 de salida, $0.00727 con el precio de `semana-07/prices.json` (fuente del autor, 2026-10-21). Latencia p50 de 1.2 s por chunk.
- **Consulta:** sin costo ni latencia adicional, porque no llama a Haiku al buscar.
- **Tamaño del índice:** 1,471,171 B (`semana8`) frente a 1,490,310 B (`semana9_ctx`), un 1.3 % más.

## Casos que cambian de acierto en recall@5

| Pregunta | ES | EN |
|---|---|---|
| `rec-34` (SKUs perecederos revisados cada semana) | pierde | pierde |
| `seg-10` (quién aprueba la compra urgente de ese SKU) | gana | gana |
| `seg-13` (¿y puede modificar precios?) | sin cambio | pierde |
| `seg-14` (¿y qué hago si me da una respuesta incorrecta?) | pierde | pierde |

Los cambios coinciden en ambos idiomas, así que vienen del índice, no de ruido de la consulta: con los mismos embeddings de consulta y un índice determinista, la diferencia es el contexto agregado.

## Lectura

- **No mejora el recall.** Baja en base (ES y EN, de 1.000 a 0.970) y en seguimiento EN (de 0.867 a 0.800). En seguimiento ES no cambia.
- **El orden mejora poco y solo en seguimiento.** MRR sube 0.016 en ES y 0.017 en EN; nDCG@10 baja ligeramente en las cuatro celdas.
- **Hipótesis (no verificada):** los contextos son largos frente al chunk (267 caracteres de media contra 348) y 51 de 57 repiten el nombre de la empresa. Ese texto común hace que los embeddings de los chunks se parezcan más entre sí y diluye lo específico de cada chunk. Además, la línea base ya está en el techo (recall@5 de 1.000 en base), así que hay poco margen para ganar.

## Conclusión

Contextual retrieval no mejora la recuperación en este corpus y no se adopta. El costo de indexado es bajo ($0.007 una sola vez) y no añade latencia en consulta, así que el problema no es el costo, es que no aporta con 24 documentos cortos y chunks que ya contienen su tema.

Una variante con contextos más cortos y sin el nombre de la empresa podría probar la hipótesis de dilución. Queda como opción, no como pendiente de esta actividad.

## Limitaciones

- Una corrida. El índice y las consultas son deterministas, pero los contextos de Haiku pueden variar si se regeneran.
- Solo búsqueda vectorial. No se probó BM25 sobre el texto con contexto (contextual BM25), que es la otra mitad de la técnica original.
- Corpus pequeño y homogéneo: el beneficio esperado de la técnica es mayor en corpus grandes, con chunks que pierden su contexto.
