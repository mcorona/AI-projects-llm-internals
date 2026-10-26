# Actividad 6 (semana 8): BM25, vectorial e híbrido con RRF

Corrida del 2026-10-26. Script: `experimentos/hibrida_bm25.py` (el mismo del commit `47da5c6`, que estaba solo en la rama `hibrida-bm25` del PR #13, sin fusionar).
Índice `semana8` en OpenSearch 2.19.1: 57 chunks (fijo 400/80) con bge-m3. Golden set de semana 8 (`datasets/recuperacion_{es,en}.jsonl`, 50 preguntas por idioma). Sin modelos generativos.

- **BM25:** `match` sobre `content`, con el analizador estándar de OpenSearch.
- **Vectorial:** k-NN con bge-m3.
- **Híbrido:** fusión RRF (k = 60) de los top 20 de BM25 y de los top 20 vectoriales.

## Resultados

| Idioma | Método | recall@5 | recall@10 | MRR |
|---|---|---|---|---|
| ES | BM25 | 0.930 | 0.970 | 0.824 |
| ES | Vectorial | **1.000** | **1.000** | 0.860 |
| ES | Híbrido RRF | 0.970 | 0.970 | **0.912** |
| EN | BM25 | 0.270 | 0.330 | 0.188 |
| EN | Vectorial | **1.000** | **1.000** | **0.834** |
| EN | Híbrido RRF | 0.770 | 0.900 | 0.582 |

MRR en este script: promedio, por pasaje de referencia, de 1/posición dentro del top 10. Es una definición distinta a la del reranking (actividad 7), que toma el primer chunk relevante por pregunta, así que los MRR de las dos tablas no se comparan directamente.

## Lectura

- **ES:** el híbrido mejora el orden (MRR de 0.860 a 0.912), pero pierde recall@5 (de 1.000 a 0.970): RRF sube al top 5 chunks que solo BM25 rankeó alto.
- **EN:** BM25 casi no funciona (recall@5 0.270), porque las preguntas están en inglés y el corpus en español: no hay términos en común. RRF le da el mismo peso que al vectorial y mete ese ruido arriba: el híbrido baja recall@5 de 1.000 a 0.770.
- **Decisión:** el híbrido no se adopta en este corpus. Para el orden, el reranking con Haiku (actividad 7) mejora más sin perder recall.

## Limitaciones

- El golden set no tiene consultas de términos exactos (códigos, IDs, SKUs), que es donde BM25 debería ayudar más. Este resultado no dice si la búsqueda híbrida vale la pena en general.
- RRF con pesos iguales. No se probaron pesos por idioma ni desactivar BM25 en consultas en otro idioma.
- Una corrida (BM25 y el índice son deterministas).
