# Actividad 8: comparación final de semana 9

Resumen de todas las técnicas medidas en semana 9 contra la misma línea base, con el mismo golden set congelado (`datasets/avanzado_{es,en}.jsonl`).
No hay corridas nuevas: cada cifra viene del archivo de resultados indicado. Todas las técnicas generativas usan claude-haiku-5-5; precios de la página oficial de Anthropic (`semana-07/prices.json`, consultada el 2026-10-26).

**Línea base:** vectorial con bge-m3 y chunking fijo 400/80 (índice `semana8` en OpenSearch).

## 1. Preguntas base (50 por idioma, autónomas)

| Técnica | Idioma | recall@5 | nDCG@10 | Costo por consulta (USD) | Latencia adicional p50 | Costo único de indexado | Decisión | Fuente |
|---|---|---|---|---|---|---|---|---|
| Vectorial (línea base) | ES | 1.000 | 0.904 | 0 | 0 | 0 | Base | semana 8 |
| Vectorial (línea base) | EN | 1.000 | 0.885 | 0 | 0 | 0 | Base | semana 8 |
| Reranking con Haiku | ES | 1.000 | **0.982** | ~0.0005 | ~2.4 s | 0 | Mejor orden | semana 8, actividad 7 |
| Reranking con Haiku | EN | 1.000 | **0.974** | ~0.0005 | ~2.4 s | 0 | Mejor orden | semana 8, actividad 7 |
| Query rewriting | ES | 1.000 | 0.898 | 0.000085 | 1.3 s | 0 | No se adopta | `reescritura.md` (2.ª corrida) |
| Query rewriting | EN | 1.000 | 0.885 | 0.000098 | 1.5 s | 0 | No se adopta | `reescritura.md` (2.ª corrida) |
| HyDE | ES | 0.960 | 0.886 | 0.000098 | 1.4 s | 0 | No se adopta | `hyde.md` |
| HyDE | EN | 0.880 | 0.816 | 0.000137 | 1.9 s | 0 | No se adopta | `hyde.md` |
| Contextual retrieval | ES | 0.970 | 0.873 | 0 | 0 | 0.0073 | No se adopta | `contextual.md` |
| Contextual retrieval | EN | 0.970 | 0.875 | 0 | 0 | 0.0073 | No se adopta | `contextual.md` |

## 2. Preguntas de seguimiento (15 por idioma, dependen de una pregunta previa)

| Técnica | Idioma | recall@5 | nDCG@10 | Costo por consulta (USD) | Latencia adicional p50 | Fuente |
|---|---|---|---|---|---|---|
| Vectorial (línea base) | ES | 0.933 | 0.809 | 0 | 0 | `reescritura.md` |
| Vectorial (línea base) | EN | 0.867 | 0.802 | 0 | 0 | `reescritura.md` |
| Query rewriting | ES | 0.800 | 0.711 | 0.000040 | 0.9 s | `reescritura.md` (2.ª corrida) |
| Query rewriting | EN | 0.933 | 0.793 | 0.000081 | 1.2 s | `reescritura.md` (2.ª corrida) |
| HyDE (con pregunta previa) | ES | 0.933 | 0.750 | 0.000097 | 1.4 s | `hyde.md` |
| HyDE (con pregunta previa) | EN | 0.933 | 0.774 | 0.000159 | 2.2 s | `hyde.md` |
| Contextual retrieval | ES | 0.933 | 0.805 | 0 | 0 | `contextual.md` |
| Contextual retrieval | EN | 0.800 | 0.798 | 0 | 0 | `contextual.md` |

Con 15 preguntas, una pregunta mueve el recall 0.067. La reescritura cambió de 1.000 a 0.933 en EN entre dos corridas del mismo código: las diferencias de una o dos preguntas son ruido.

## 3. Preguntas multi-salto (10 por set e idioma, dos documentos por pregunta)

"Ambos" cuenta las preguntas con los dos pasajes en el top 5. El set puente es el caso más favorable para GraphRAG (la entidad que une los documentos no aparece en la pregunta).

| Técnica | Compuestas ES | Compuestas EN | Puente ES | Puente EN | Costo por consulta (USD) | Latencia p50 | Costo único |
|---|---|---|---|---|---|---|---|
| Vectorial (línea base) | 9/10 | 7/10 | 9/10 | 5/10 | 0 | ~25 ms | 0 |
| Vector + reranking | **10/10** | **10/10** | **10/10** | **10/10** | ~0.0005 | ~2.3 s | 0 |
| GraphRAG por expansión (G) | **10/10** | 8/10 | 8/10 | 6/10 | 0 | ~25 ms | 0.048 |
| GraphRAG con entidades de la pregunta (G+Q) | 9/10 | 9/10 | **10/10** | 7/10 | 0.00014–0.00016 | ~1.8 s | 0.048 |

Fuente: `graphrag.md`.

## 4. Seguridad: permisos y multi-tenant (criterio no negociable)

| Prueba | pgvector | Qdrant | OpenSearch | Sin filtro (contraste) | Fuente |
|---|---|---|---|---|---|
| Fuga de permisos por rol (300 consultas por base e idioma) | **0** | **0** | **0** | ~66 % de chunks no autorizados | `permisos.md` |
| Pasajes prohibidos devueltos (5 casos por idioma) | **0/5** | **0/5** | **0/5** | 5/5 | `permisos.md` |
| Fuga entre tenants (100 consultas por base e idioma) | **0** | **0** | **0** | 36–38 % (alfa) y 62–64 % (beta) del otro tenant | `multitenant.md` |
| Cifra del otro tenant en textos casi idénticos (20 casos) | **0/20** | **0/20** | **0/20** | sale primero en 10/20 | `multitenant.md` |

El filtro no tiene costo de API. El recall@5 con filtro (0.991) coincide exactamente con lo que los permisos dejan ver.

## Mejora en recall frente a mejora en costo y latencia

- **Recall:** ninguna técnica de semana 9 mejora el recall@5 de la línea base en las preguntas base, que ya está en 1.000. En multi-salto, la única técnica que lleva todos los grupos a 10/10 es el reranking de semana 8. GraphRAG con entidades (G+Q) mejora el vectorial en inglés, pero no alcanza al reranking.
- **Orden (nDCG@10):** el reranking es la única técnica que lo mejora con claridad (ES 0.904 → 0.982; EN 0.885 → 0.974). Reescritura, HyDE y contextual retrieval lo dejan igual o lo bajan.
- **Costo:** contextual retrieval y GraphRAG por expansión no tienen costo por consulta (solo indexado único de $0.007 y $0.048). Reescritura y HyDE cuestan entre $0.00004 y $0.00016 por consulta sin mejorar. El reranking es el más caro por consulta (~$0.0005), y el único que paga su costo con mejor orden.
- **Latencia:** reranking añade ~2.3–2.4 s; HyDE, 1.4–2.2 s; reescritura, 0.9–1.5 s; G+Q, ~1.8 s. Contextual retrieval, GraphRAG por expansión y los filtros de permisos no añaden latencia por llamada a modelo.

## Decisión para el pipeline

Vectorial (bge-m3, fijo 400/80) con filtro de tenant y roles dentro de la consulta, y reranking con Haiku cuando el orden importa o la pregunta toca dos documentos. Reescritura, HyDE, contextual retrieval y GraphRAG no se adoptan en este corpus.

## Límites de esta comparación

- Corpus pequeño (24 documentos, 57 chunks): la línea base ya está en el techo de recall en preguntas base, y el top 20 vectorial cubre el 35 % del corpus, lo que favorece al reranking.
- Una corrida por técnica (dos en reescritura). Haiku no es determinista.
- Las latencias vienen de corridas distintas, en la misma Mac, y no se midieron en un banco común.
- Todas las técnicas generativas se probaron solo con Haiku 5.5.
