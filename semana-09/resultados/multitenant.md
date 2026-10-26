# Actividad 6: aislamiento multi-tenant

Corrida del 2026-10-26. Script: `experimentos/multitenant.py`. Sin llamadas a modelos generativos: costo de API 0.

## Tenants de prueba

- **alfa:** los 24 documentos de semana 8 (57 chunks).
- **beta:** `corpus_beta/`, 10 documentos copiados de alfa. Cada uno difiere de su par en una sola línea: la cifra del pasaje de referencia (por ejemplo, plazo de devolución de 30 a 20 días; factor de seguridad de SKUs críticos de 1.5 a 2.0). 33 chunks. Generado y validado por `datasets/construir_multitenant.py`: cada pasaje cambiado aparece una vez y queda completo dentro de un chunk en ambos tenants.

Ambos tenants están en los mismos índices: `semana9.chunks_mt` en pgvector 0.8.6, `semana9_mt` en Qdrant 1.12.4 y `semana9_mt` en OpenSearch 2.19.1, con `tenant_id` y `roles`. El filtro va dentro de la consulta, igual que en la actividad 5. Los índices de las actividades anteriores no se tocaron.

## Cómo se mide

- **Barrido:** 50 preguntas base × 2 tenants, con un usuario que tiene todos los roles, para que solo actúe el filtro de tenant. La fuga se juzga contra el `tenant_id` y `permisos.json`.
- **Casos solapados** (`datasets/multitenant_{es,en}.jsonl`): las 10 preguntas cuyo pasaje existe casi idéntico en ambos tenants, hechas desde alfa y desde beta, con un rol que ve el documento. Son 20 casos por base e idioma.
- **Contraste sin filtro:** el mismo barrido sin filtro, separado por tenant (cuántos chunks del otro tenant vería cada usuario).
- **Resultados cortos:** búsquedas filtradas con menos de k chunks aunque haya k visibles.

## Resultados

| Base | Idioma | Barrido (pregunta × tenant) | Fuga con filtro | Chunks del otro tenant sin filtro (top 10 de alfa / de beta) | Casos solapados | Cifra propia en top 5 (con filtro) | Cifra del otro tenant devuelta (sin / con filtro) | Otro tenant antes que el propio (sin filtro) | Resultados cortos |
|---|---|---|---|---|---|---|---|---|---|
| pgvector | es | 100 | **0** | 185 / 315 | 20 | 20/20 | 20/20 / **0/20** | 10/20 | 0 |
| Qdrant | es | 100 | **0** | 191 / 309 | 20 | 20/20 | 20/20 / **0/20** | 10/20 | 0 |
| OpenSearch | es | 100 | **0** | 186 / 314 | 20 | 20/20 | 20/20 / **0/20** | 10/20 | 0 |
| pgvector | en | 100 | **0** | 181 / 319 | 20 | 20/20 | 20/20 / **0/20** | 10/20 | 0 |
| Qdrant | en | 100 | **0** | 187 / 313 | 20 | 20/20 | 20/20 / **0/20** | 10/20 | 0 |
| OpenSearch | en | 100 | **0** | 180 / 320 | 20 | 20/20 | 20/20 / **0/20** | 10/20 | 0 |

Fuga total con filtro, incluida la cifra del otro tenant: **0**. Código de salida 0.

## Lectura

- **Aislamiento total con filtro:** fuga 0 en las tres bases y en ambos idiomas. Ninguna consulta devolvió la cifra del otro tenant, aunque los chunks son casi idénticos.
- **Cada tenant recibe su propia respuesta:** 20 de 20 casos solapados tienen la cifra propia en el top 5.
- **Sin filtro, el riesgo es alto:** un usuario de alfa vería entre 180 y 191 chunks de beta de 500 (36 a 38 %), y uno de beta entre 309 y 320 chunks de alfa (62 a 64 %). En los casos solapados, la cifra del otro tenant aparece en el top 10 en 20 de 20, y sale antes que la propia en 10 de 20. Con texto casi idéntico, el orden entre tenants es prácticamente aleatorio, así que sin filtro un usuario recibiría la cifra de la otra empresa la mitad de las veces.
- **Sin resultados cortos:** el filtro no deja ninguna búsqueda con menos de k resultados.

## Corrección durante la actividad

La primera versión sumaba en una sola columna los chunks del otro tenant sin filtro, para ambos usuarios. Esa suma da siempre 10 por pregunta (500 en total) por construcción, porque sin filtro el resultado es el mismo para los dos usuarios. Se separó por tenant. Fuga, casos solapados y resultados cortos no cambiaron entre corridas.

## Limitaciones

- Dos tenants en índices compartidos, separados por filtro. No se probó aislamiento físico (un índice o colección por tenant).
- El tenant beta tiene 10 documentos: el contraste sin filtro depende de ese tamaño.
- Un rol por usuario en los casos solapados. Los permisos y tenants son sintéticos.
- No se midió la latencia con filtro frente a sin filtro.
