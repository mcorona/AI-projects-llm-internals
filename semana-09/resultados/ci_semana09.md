# Actividad 9: eval de recuperación y permisos en CI

Workflow: `.github/workflows/recuperacion-semana-09.yml`, en cada PR que toque `semana-09/**`. Script: `ci/permisos_ci.py`.
Base: pgvector de servicio (`pgvector/pgvector:pg16`, pgvector 0.8.7 con `hnsw.iterative_scan = strict_order`), con los tenants alfa (57 chunks) y beta (33 chunks), `tenant_id` y `roles`, y el filtro dentro de la consulta.
Embeddings: `text-embedding-3-small` (OpenAI, secreto `OPENAI_API_KEY`), porque bge-m3 corre en LM Studio y no está en GitHub Actions. Costo aproximado: $0.0003 por corrida. Sin modelos de Anthropic.

## Qué hace fallar el check

1. recall@5 de las 50 preguntas base (usuario de alfa con todos los roles) bajo el umbral en ES o EN.
2. Cualquier fuga por rol: chunks no autorizados en el top 10 (50 preguntas × 6 roles) o pasajes prohibidos devueltos (5 casos por idioma).
3. Cualquier fuga entre tenants: chunks del otro tenant (50 preguntas × 2 tenants) o la cifra del otro tenant en los 20 casos casi idénticos.

La fuga no tiene umbral: debe ser 0.

## Calibración con la primera corrida

Run de GitHub Actions `40390705860` (PR #29, 2026-10-26).

| Idioma | recall@5 | Umbral | Margen | Fuga por rol | Prohibidos devueltos | Fuga entre tenants | Cifra del otro tenant | Cifra propia en top 5 |
|---|---|---|---|---|---|---|---|---|
| ES | 0.990 | 0.90 | 0.090 | 0 | 0/5 | 0 | 0/20 | 20/20 |
| EN | 0.950 | 0.90 | 0.050 | 0 | 0/5 | 0 | 0/20 | 20/20 |

El recall coincide con el CI de semana 8 (`semana-08/resultados/ci_recuperacion.md`: ES 0.990, EN 0.950), con el mismo modelo y el mismo corpus de alfa: agregar el tenant beta con el filtro activo no cambió el recall de alfa.

**Decisión:** se mantiene `UMBRAL = 0.90`. Con 50 preguntas, cada una vale 0.02 de recall: en EN el umbral deja margen de dos preguntas antes de fallar. Subirlo a 0.95 haría fallar el check en EN con cualquier variación mínima.

## Incidentes

- **Primera corrida (run `40390060225`):** falló por un HTTP 500 de la API de embeddings de OpenAI al embeber las preguntas; no fue fuga ni recall. Se agregaron reintentos con espera creciente solo para errores transitorios (429 y 5xx), hasta 4 intentos. En la corrida de calibración no hizo falta reintentar.

## Pendientes de mantenimiento

GitHub anotó dos avisos en el run, sin efecto hoy en el resultado:
- `actions/checkout@v4` y `actions/setup-python@v5` usan Node.js 20, que está obsoleto en los runners.
- `ubuntu-latest` migra a Ubuntu 26 desde el 19 de octubre de 2026.

Afectan también a los workflows de semanas 6 a 8; conviene actualizarlos juntos.

## Límites

- En CI solo corre pgvector. Qdrant y OpenSearch se verificaron con fuga 0 localmente (actividades 5 y 6).
- El CI usa `text-embedding-3-small`, no el bge-m3 de las mediciones locales.
- Una corrida de calibración.
