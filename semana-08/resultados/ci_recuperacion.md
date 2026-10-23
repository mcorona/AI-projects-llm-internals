# Actividad 9: calibración del umbral de la eval de recuperación en CI

Run de GitHub Actions: `39877067557` (workflow `recuperacion-semana-08`, PR #15).
Modelo: `text-embedding-3-small` (OpenAI), base `pgvector/pgvector:pg16` de servicio, 57 chunks fijos (400/80), 50 consultas por idioma.

| Idioma | recall@5 en CI | Umbral | Margen |
|---|---|---|---|
| ES | 0.990 | 0.90 | 0.090 |
| EN | 0.950 | 0.90 | 0.050 |

Estos valores coinciden con la corrida local del mismo modelo (`embeddings_fijo_400_solape_80.md`: ES 0.990, EN 0.950), así que CI reproduce la medición local.

Decisión: se mantiene `UMBRAL = 0.90`. Con 50 consultas por idioma, cada pregunta equivale a 0.02 de recall. En EN, perder tres preguntas (0.90) ya está en el límite, así que el umbral deja margen de dos preguntas antes de fallar. Subirlo a 0.95 haría fallar el check en EN con la configuración actual.

Límites: es una sola corrida de CI. El recall de un modelo de OpenAI puede variar entre versiones del servicio, y la muestra es pequeña.
