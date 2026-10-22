# Actividad 3: modelos de embeddings (chunking fijo 400, solape 80)

Corrida del 2026-10-22. 57 chunks, 50 consultas por idioma. Recall por pasaje de referencia.

| Modelo | Idioma | Dimensión | recall@5 | recall@10 | Tokens (chunks + consultas) | Costo (USD) |
|---|---|---|---|---|---|---|
| bge-m3 (local) | ES | 1024 | 1.000 | 1.000 | no aplica | 0 (local) |
| bge-m3 (local) | EN | 1024 | 1.000 | 1.000 | no aplica | 0 (local) |
| text-embedding-3-small | ES | 1536 | 0.990 | 1.000 | 6472 | 0.000129 |
| text-embedding-3-small | EN | 1536 | 0.950 | 0.980 | 6221 | 0.000124 |
| text-embedding-3-large | ES | 3072 | 1.000 | 1.000 | 6472 | 0.000841 |
| text-embedding-3-large | EN | 3072 | 1.000 | 1.000 | 6221 | 0.000809 |
| gemini-embedding-2 | ES | 3072 | 0.980 | 1.000 | no reportados | pendiente: $0.20 por millón de tokens de entrada |
| gemini-embedding-2 | EN | 3072 | 0.980 | 1.000 | no reportados | pendiente: $0.20 por millón de tokens de entrada |

Precios: OpenAI en https://developers.openai.com/api/docs/models (consultado 2026-10-22). Precio de Gemini: $0.20 por millón de tokens de entrada, indicado por el autor; falta la URL exacta para citarla. El script no registra tokens de Gemini, así que su costo por corrida queda pendiente.

Lectura: bge-m3 y text-embedding-3-large empatan en el máximo. bge-m3 es local, sin costo de API, y su dimensión (1024) coincide con la columna `doc_chunks.embedding` de inventory-copilot. Las diferencias son de uno o dos pasajes de 50 consultas: no son concluyentes por sí solas.

Limitación para CI: bge-m3 corre en LM Studio, que no está disponible en GitHub Actions. Si la eval de recuperación corre en CI (actividad 9), habrá que usar OpenAI en CI o guardar los vectores precalculados.
