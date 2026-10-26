# Actividad 5: filtros por metadatos y ACLs

Corrida del 2026-10-26. Script: `experimentos/permisos.py`. Sin llamadas a modelos generativos: costo de API 0.

Los 57 chunks de semana 8 (fijo 400/80, bge-m3) se cargaron en índices nuevos con `tenant_id = "alfa"` y los `roles` de su documento según `datasets/permisos.json` (modelo sintético de prueba):
pgvector (`semana9.chunks`, pgvector 0.8.6), Qdrant (`semana9_acl`, v1.12.4) y OpenSearch (`semana9_acl`, 2.19.1). Los índices de semana 8 no se tocaron.

## Dónde va el filtro

El filtro va dentro de la consulta de búsqueda en las tres bases, no se aplica sobre resultados ya recuperados:

- **pgvector:** `WHERE tenant_id = %s AND roles && %s::text[]` en la misma SQL del `ORDER BY embedding <=> ...`. Con `hnsw.iterative_scan = strict_order` (pgvector ≥ 0.8), el índice HNSW sigue buscando hasta llenar k con filas que cumplen el filtro.
- **Qdrant:** `filter` con `must` sobre `tenant_id` y `roles` (match any) dentro de `points/query`, con índices de payload `keyword` en ambos campos.
- **OpenSearch:** `filter` (bool con `term` y `terms`) dentro de la cláusula `knn`, que filtra durante la búsqueda en lugar de después.

## Cómo se mide

- **Fuga de permisos:** chunks del top 10 devueltos a un usuario cuyo tenant no coincide o cuyos roles no intersecan los del documento. Se juzga contra `permisos.json`, no contra lo que guarda la base, así que un error de carga también contaría como fuga.
- **Barrido:** 50 preguntas base × 6 roles = 300 consultas por base e idioma, con filtro y sin filtro (contraste).
- **recall@5 con filtro frente a sin filtro:** en los 112 pares pregunta–rol donde el rol puede ver el documento de referencia.
- **Casos de permiso del golden set:** 5 permitidos (recall@5) y 5 prohibidos (el pasaje no debe aparecer).
- **Resultados cortos:** búsquedas filtradas que devuelven menos de k chunks aunque haya k visibles.

## Resultados

| Base | Idioma | Consultas | Fuga con filtro | Chunks no autorizados sin filtro | recall@5 sin filtro | recall@5 con filtro | Permitidos recall@5 (sin / con) | Prohibidos devueltos (sin / con) | Resultados cortos |
|---|---|---|---|---|---|---|---|---|---|
| pgvector | es | 300 | **0** | 1983 | 1.000 | 0.991 | 1.000 / 1.000 | 5/5 / **0/5** | 0 |
| Qdrant | es | 300 | **0** | 1983 | 1.000 | 0.991 | 1.000 / 1.000 | 5/5 / **0/5** | 0 |
| OpenSearch | es | 300 | **0** | 1974 | 1.000 | 0.991 | 1.000 / 1.000 | 5/5 / **0/5** | 0 |
| pgvector | en | 300 | **0** | 1980 | 1.000 | 0.991 | 1.000 / 1.000 | 5/5 / **0/5** | 0 |
| Qdrant | en | 300 | **0** | 1980 | 1.000 | 0.991 | 1.000 / 1.000 | 5/5 / **0/5** | 0 |
| OpenSearch | en | 300 | **0** | 1984 | 1.000 | 0.991 | 1.000 / 1.000 | 5/5 / **0/5** | 0 |

Fuga total con filtro: **0**. El script sale con código 0; con cualquier fuga sale con código 1.

## Lectura

- **Fuga 0 en las tres bases y en ambos idiomas.** El criterio no negociable se cumple con un solo tenant (la prueba entre tenants va en la actividad 6).
- **Sin filtro, el riesgo es real:** cerca de 1,980 de los 3,000 chunks devueltos (66 %) no estaban autorizados para el usuario, y los 5 pasajes prohibidos del golden set aparecían todos.
- **El recall de 0.991 con filtro es el comportamiento correcto, no una pérdida.** Se reproduce exactamente solo con los permisos: en `rec-47`, el rol `compras` no puede ver `transferencias_cedis.md`, y en `rec-49`, el rol `almacen` no puede ver `ordenes_de_compra.md`. Son preguntas con dos pasajes de referencia, y el filtro oculta el que el usuario no puede ver. Los 5 casos permitidos mantienen recall@5 de 1.000.
- **Sin resultados cortos.** En pgvector, `iterative_scan` evita que el filtro deje la búsqueda HNSW con menos de k resultados.
- **Diferencias pequeñas sin filtro** (1,974 a 1,984) entre bases vienen de que cada motor ordena distinto los vecinos aproximados de la cola del top 10. No afectan la fuga con filtro.

## Limitaciones

- Un solo tenant (`alfa`). El aislamiento entre tenants se prueba en la actividad 6.
- Permisos a nivel de documento, con un rol por usuario. No se probaron usuarios con varios roles ni permisos por chunk.
- Roles sintéticos (`permisos.json`), no permisos reales de inventory-copilot.
- Corpus pequeño (57 chunks): con muchos más documentos, el filtrado dentro de HNSW se vuelve más exigente y habría que volver a medir resultados cortos y latencia.
- No se midió la latencia con filtro frente a sin filtro.
