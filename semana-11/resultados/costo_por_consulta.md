# Semana 11 · Actividad 7: costo y latencia por consulta

Pipeline decidido en las actividades 2 a 6:
- **Recuperación:** bge-m3 local, pgvector con filtro de tenant y roles (top 20) y reranking con Haiku 5.5.
- **Generación:** Haiku 5.5 medium sobre el top 5, con el prompt `solo_documentos`.
- **Evaluación:** la suite de generación, con Haiku 5.5 low como juez.

Se corrió sobre las 150 preguntas del golden set: 65 respondibles y 10 sin respuesta por idioma.

- **Tokens:** los que reporta la API en cada llamada.
- **Precios:** `semana-07/prices.json`; Haiku 5.5 cuesta $0.10 por millón de tokens de entrada y $0.50 por millón de salida.
- **Script:** `experimentos/costo_por_consulta.py`.
- **Salida completa:** `costo_por_consulta_salida.txt`.

## Costo y latencia por etapa (medias por consulta)

| Etapa | Tokens de entrada | Tokens de salida | USD por consulta | p50 (s) | p95 (s) | Nota |
|---|---|---|---|---|---|---|
| Recuperación: embedding (bge-m3) | 0 | 0 | $0.00000 | 0.05 | 0.05 | local, sin costo de API |
| Recuperación: búsqueda pgvector | 0 | 0 | $0.00000 | 0.00 | 0.00 | top 20 con filtro |
| Recuperación: reranking (Haiku) | 3,350 | 316 | $0.00049 | 2.41 | 4.05 | 20 candidatos |
| **Recuperación total** | 3,350 | 316 | **$0.00049** | **2.46** | **4.11** | |
| **Generación** (Haiku medium) | 1,023 | 210 | **$0.00021** | **1.58** | **2.78** | top 5, prompt solo_documentos |
| **Respuesta al usuario** (recuperación + generación) | 4,373 | 526 | **$0.00070** | **4.18** | **6.23** | lo que paga producción |
| **Evaluación**, respondible (4 métricas) | 9,056 | 1,007 | **$0.00141** | **17.17** | **26.73** | 7.1 llamadas al juez |
| **Evaluación**, sin respuesta (abstención) | 363 | 19 | **$0.00005** | **0.75** | **1.21** | 1 llamada |

### Evaluación por métrica (respondibles)

| Métrica | p50 (s) | p95 (s) |
|---|---|---|
| faithfulness (RAGAS) | 5.61 | 8.88 |
| answer_relevancy (RAGAS) | 8.70 | 16.45 |
| exactitud (juez propio) | 0.97 | 3.47 |
| clase (abstención) | 0.81 | 2.03 |

## Costo de evaluar cada suite completa una vez (una corrida de CI)

| Suite | Qué incluye | Costo |
|---|---|---|
| Recuperación, métricas exactas | 130 consultas respondibles: embedding, búsqueda y reranking | $0.064 |
| Recuperación con RAGAS (context precision y recall) | lo anterior más el juez ($0.00157 por consulta, actividad 2) | $0.268 |
| Generación | 150 respuestas sobre contextos fijos, más su evaluación | $0.215 |
| **Las dos suites, con métricas exactas en recuperación** | | **$0.279** |
| Las dos suites, con RAGAS también en recuperación | | $0.483 |

## Lectura

- **Producción:**
  - Una respuesta cuesta $0.0007, es decir, unas 1,400 consultas por dólar.
  - El reranking es el 70 % del costo y el 58 % de la latencia mediana.
  - El embedding y la búsqueda no cuestan nada y tardan menos de 0.1 s.
- **Evaluar cuesta más que responder:**
  - Evaluar una consulta respondible cuesta el doble de lo que cuesta responderla ($0.00141 contra $0.00070).
  - Necesita 7 llamadas al juez: RAGAS parte la respuesta en afirmaciones y las verifica una por una, y answer relevancy genera preguntas.
  - Las dos métricas de RAGAS concentran la latencia de la evaluación.
- **CI:**
  - Las dos suites cuestan $0.28 por corrida. Con RAGAS también en recuperación, el costo casi se duplica ($0.48).
  - Como el reranking ya se distingue con métricas exactas (recall@3 y AP@5, actividad 2), la actividad 8 puede usar métricas exactas en recuperación y las 150 preguntas completas en generación, sin subconjunto.
  - Si el costo llega a importar, el recorte con más efecto está en la evaluación de generación, no en la recuperación.
- **Cómo se midieron las latencias:**
  - La recuperación corrió en serie, una consulta a la vez, así que su latencia es la de una consulta sola.
  - La generación corrió con 4 hilos y la evaluación con 8 consultas en paralelo, y dentro de cada consulta las métricas van en serie. Sus latencias incluyen la espera de la API bajo esa concurrencia.

## Corridas

- **Corrida 1** (`costo_por_consulta_salida_corrida1.txt`): falló la red local.
  - 33 métricas fallaron en 18 consultas (errores de conexión, timeouts y reintentos agotados de Instructor).
  - Hubo bloqueos de hasta 15 minutos, que inflaron la p95 de la evaluación a 579 s.
  - Se descartaron 20 evaluaciones: las 18 con error y 2 que tardaron más de 60 s en alguna métrica.
- **Corrida final:**
  - Solo se volvieron a evaluar esas 20.
  - Recuperación, generación y las 130 evaluaciones limpias salieron de la caché (`costo_por_consulta_cache.json`).
  - Errores del juez: 0.
  - Las cifras de las tablas suman las 150 consultas medidas, en las corridas 1 y final.
- **Gasto real de la actividad:** ≈ $0.31 ($0.28 de la corrida 1 y ≈ $0.03 de la reevaluación).
