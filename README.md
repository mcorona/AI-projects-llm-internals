# AI-projects-llm-internals

Laboratorio de la Fase 1 del programa "Experto en GenAI para Negocios Internacionales": fundamentos de LLMs, construidos desde cero siguiendo la serie Zero to Hero de Andrej Karpathy, en MLX (Apple Silicon).

## Estructura

| Carpeta / archivo | Contenido |
|---|---|
| `semana-01/` | Bigram (PyTorch y MLX), atención causal, mini-GPT, entrenamiento y práctica de memoria del KV cache |
| `semana-01/README.md` | Notas de la semana: resultados, glosario y decisiones |

## Requisitos

- macOS con Apple Silicon.
- [uv](https://docs.astral.sh/uv/) y Python 3.13.

## Cómo correr la semana 1

```bash
uv sync
cd semana-01
./get_data.sh
uv run python bigram_mlx.py
uv run python attention_mlx.py
uv run python minigpt_mlx.py
uv run python train_minigpt_mlx.py
uv run python practica_kv_cache.py
```

## Criterio de salida de la Fase 2

Cada semana de la Fase 2 se cierra solo si cumple lo siguiente:

- [x] Los prompts y las evals viven en Git con versión (`semana-05/prompts/`, `semana-06/golden/`).
- [x] Hay una eval automática de regresión (`semana-06/evaluar.py`) que corre en GitHub Actions cuando cambian prompts, evals o `semana-07/`.
- [x] Los cambios de prompt o modelo entran por pull request, no por push directo a `main`, con la protección de rama `ProteccionRama` y el check `regresion` como requisito (verificado con el PR #2).
- [x] La eval de NLQ (semana 7) corre en cada PR, con Haiku sobre el set difícil y una base de CI con datos sintéticos de semilla 42. Verificada en el PR #3 (exactitud 0.953 en español y 1.000 en inglés); umbral 0.90 desde el PR siguiente.
- [x] Cada semana publica sus resultados en su README, con costo y exactitud por modelo.

Lo que no cumple el criterio queda marcado como pendiente hasta que se resuelva.

## Criterio de salida de la Fase 3

La Fase 3 cubre las semanas 8 a 12: recuperación, RAG avanzado, asistente integrado (8 a 10), evaluación de RAG (11) y RAG administrado en la nube (12). Solo se marca lo verificado con evidencia en el repo.

- [x] La eval de recuperación corre en CI en cada PR que toca `semana-08/**` o `semana-09/**`, con umbral de recall@5 por idioma (0.90), calibrado con la primera corrida (ES 0.990, EN 0.950). Verificado en los PR #15 y #17 para semana 8 (`semana-08/resultados/ci_recuperacion.md`) y en el PR #29 para semana 9 (`semana-09/resultados/ci_semana09.md`).
- [x] Hay una comparación documentada de chunking, embeddings y bases vectoriales con recall@k, latencia y costo, en ES y EN (`semana-08/README.md`, actividades 2 a 5; chunking en `semana-08/resultados/chunking.md`, registrado el 2026-10-26).
- [x] La búsqueda híbrida y el reranking se miden contra la línea base. Reranking: nDCG@10 ES 0.904 → 0.982, EN 0.885 → 0.974. Híbrida (BM25 + vectorial con RRF): no mejora recall@5 (ES 1.000 → 0.970, EN 1.000 → 0.770) y no se adopta (`semana-08/resultados/hibrida.md`).
- [x] Las respuestas con citas se evalúan con juez, con exactitud y precisión de citas reportadas (`semana-08/README.md`, actividad 8).
- [x] Las técnicas avanzadas (reescritura, HyDE y contextual retrieval) se miden con el mismo golden set congelado, y se adoptan solo si mejoran. Las tres están medidas; ninguna mejora a la línea base y ninguna se adopta (`semana-09/resultados/comparacion_final.md`; PR #19, #20, #21 y #23).
- [x] Los filtros por tenant y roles se aplican dentro de la consulta en pgvector, Qdrant y OpenSearch, con fuga de permisos igual a 0 y prueba cruzada entre tenants. Criterio no negociable. Verificado con fuga 0 en las tres bases (PR #25 y #26) y con un check de CI que falla ante cualquier fuga en cada PR de semana 9 (PR #29).
- [x] El text-to-SQL sobre un esquema legado (vistas con nombres crípticos) se mide por ejecución en tres variantes (sin diccionario, con diccionario completo y con diccionario recuperado) contra el esquema original con el mismo modelo, con costo y latencia. Verificado con Sonnet 5.5 y Haiku 5.5 sobre el set difícil de semana 7: con Haiku, sin diccionario ES 0.884 / EN 0.953, diccionario completo 0.977 / 1.000 ($0.00033 por pregunta), diccionario recuperado 0.767 / 0.721; esquema original 0.977 / 1.000 (`semana-10/resultados/sql_legado.md`; PR #35 y #37).
- [x] Los documentos no textuales (PDFs con tablas, escaneos con OCR e imágenes) se extraen e indexan, y se mide su exactitud contra la referencia congelada (exactitud por celda, tasa de error por carácter y respuestas correctas) y el recall después de indexar. Verificado: filas íntegras pypdf 0/13, pdfplumber y Haiku 13/13 (PR #38); CER Tesseract 0.009, Haiku 0.001 (PR #39); hechos asociados en imágenes Tesseract 0/7, Haiku 7/7 (PR #40); recall@5 de lo extraído medido en las tres y en CI (1.000 por idioma, PR #44).
- [x] El asistente integrado (NLQ + RAG documental) se mide por tipo de pregunta (SQL, documental, no textual y mixta): ruteo, exactitud con citas, costo y latencia. Su seguridad es no negociable: cero escrituras SQL, fuga 0 por rol y entre tenants a través del asistente, y ninguna instrucción inyectada en documentos ejecutada, con check en CI. Verificado: ruteo ES 0.882 / EN 0.863 (PR #41); exactitud con juez 0.961 / 0.980 frente a 0.294 solo SQL y 0.608 solo documentos, con precisión de citas, costo ($0.00083 por pregunta) y latencia (p50 5.3 s) por tipo (PR #42); con la NLQ endurecida, 0 escrituras, fuga 0 en 128 casos y 0/48 instrucciones obedecidas (PR #43); check `eval-semana-10` en cada PR de semana 10 (PR #44). Las pruebas de seguridad encontraron que la conexión SQL de la actividad 7 permitía escribir objetos grandes (`lo_create`); se corrigió y el asistente usa la NLQ endurecida desde el PR #44 (`semana-10/README.md`).
- [ ] La recuperación y la generación se evalúan con suites separadas: recall@k para la recuperación, y faithfulness y answer relevance (RAGAS) para la generación, con costo por consulta. Semana 11.
- [ ] La misma base documental se monta en un RAG administrado de AWS (Bedrock Knowledge Bases) y de una segunda nube (Azure AI Search o Vertex AI Search), y se compara su calidad, latencia y costo con el mismo golden set. Semana 12.

Lo que no cumple el criterio queda marcado como pendiente hasta que se resuelva.

## Estado

- Semana 1: completa. Mini-GPT de 2000 pasos con pérdida de validación de 1.72 (n=128, lr=1e-3). Ver `semana-01/README.md`.
- Semana 10: completa (text-to-SQL sobre esquema legado, documentos no textuales y asistente integrado con seguridad y CI). Ver `semana-10/README.md`.
- Fase 3: en curso. Criterios 1 a 9 (semanas 8 a 10) verificados; faltan los de las semanas 11 (evaluación de RAG) y 12 (RAG administrado).
