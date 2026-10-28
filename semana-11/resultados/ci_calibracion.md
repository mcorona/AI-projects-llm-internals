# Semana 11 · Actividad 8: calibración de umbrales del CI

Workflow `.github/workflows/eval-semana-11.yml`, en cada PR que toque `semana-11/**`. Tiene dos jobs separados, uno por suite:

- **recuperacion:** reconstruye `semana10.chunks` en el pgvector de servicio, toma el top 20 con filtro de tenant y roles, aplica reranking con Haiku 5.5 y calcula métricas exactas sobre las 65 respondibles por idioma.
- **generacion:** usa los contextos fijos de la actividad 4, el generador Haiku 5.5 medium con el prompt `solo_documentos` y el juez Haiku 5.5 low. Corre las 150 preguntas.

Script: `semana-11/ci/eval_ci.py`.

**Subconjunto en generación: no.**
- La tabla de la actividad 7 estimaba ≈ $0.22 por corrida de la suite de generación.
- La corrida de calibración costó $0.158.
- Las dos suites juntas cuestan ≈ $0.22 por PR.

**En recuperación no se usa RAGAS:**
- Context precision equivale a AP@5 con juez (Pearson 0.84, actividad 2).
- Haría la suite de recuperación unas 4 veces más cara (actividad 7).
- El reranking ya se detecta con recall@3 y AP@5.

**Regla (semana 10, fijada antes de correr):** umbral = múltiplo de 0.05 inmediatamente inferior a (valor de la primera corrida − máx(0.03, 1/n)).
- n es el número de preguntas por idioma: 65 respondibles y 10 sin respuesta.
- Los valores de CI difieren de los locales porque en CI los embeddings son `text-embedding-3-small` (OpenAI), no bge-m3. Por eso se calibra con la corrida de CI.

**Corrida de calibración:** PR #57, 2026-10-28, con `--calibrar`.

## Recuperación (n = 65 por idioma)

| Métrica | ES | Umbral ES | EN | Umbral EN |
|---|---|---|---|---|
| recall@3 | 1.000 | 0.95 | 0.985 | 0.95 |
| recall@5 | 1.000 | 0.95 | 1.000 | 0.95 |
| MRR | 0.931 | 0.90 | 0.958 | 0.90 |
| nDCG@10 | 0.951 | 0.90 | 0.971 | 0.90 |
| AP@5 | 0.933 | 0.90 | 0.955 | 0.90 |

- Reranking fallido: 0/130.
- Costo: $0.064.
- Duración del paso: 76 s.

## Generación (n = 65 respondibles y 10 sin respuesta por idioma)

| Métrica | ES | Umbral ES | EN | Umbral EN |
|---|---|---|---|---|
| faithfulness (RAGAS) | 0.833 | 0.80 | 0.829 | 0.75 |
| answer relevancy (RAGAS) | 0.850 | 0.80 | 0.819 | 0.75 |
| exactitud (juez propio) | 1.000 | 0.95 | 1.000 | 0.95 |
| precisión de citas | 0.728 | 0.65 | 0.759 | 0.70 |
| no abstención falsa | 1.000 | 0.95 | 1.000 | 0.95 |
| abstención correcta (n = 10) | 1.000 | 0.90 | 1.000 | 0.90 |

- Llamadas al juez: 685.
- Métricas sin puntaje: 1 de 470, por un `InstructorRetryException` de faithfulness. La tolerancia es del 1 %.
- Costo: generación $0.028 + evaluación $0.130 = $0.158.
- Duración del paso: 154 s.

## Margen contra el ruido

La regla deja al menos 0.03 de margen.

| Métrica | Margen más estrecho | Ruido medido en la actividad 6 (otra corrida sin cambios) |
|---|---|---|
| MRR | 0.031 (ES) | 0.021 |
| AP@5 | 0.033 (ES) | 0.015 |
| faithfulness | 0.033 (ES) | 0.031 |

- El margen cubre el ruido medido, pero en faithfulness la holgura es mínima.
- **Si el job de generación falla solo por faithfulness y ningún archivo de generación cambió:** primero se vuelve a correr. Si se repite, se trata como regresión.
