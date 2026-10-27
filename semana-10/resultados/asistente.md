# Actividad 7 · Asistente integrado (NLQ + RAG documental) con citas

Script: `experimentos/asistente.py`. Golden set: `datasets/integrado_{es,en}.jsonl` (51 preguntas por idioma: 15 sql, 15 documentales, 15 no textuales y 6 mixtas), congelado en la actividad 1. Métricas fijadas antes de correr; no cambiaron entre corridas.

## Diseño

| Pieza | Elección | Origen |
|---|---|---|
| Ruteo | Haiku 5.5 low, clasifica en sql, documental o mixta | Actividad 6 |
| Herramienta NLQ | Haiku 5.5 low con DDL legado + diccionario completo, ejecutada con el rol de solo lectura `copilot_ro` (`search_path = legado`, tiempo límite 5 s) | Actividad 2 |
| Herramienta documental | pgvector `semana10.chunks` (30 documentos, 68 chunks), filtro de tenant y roles dentro de la consulta, top 20 con bge-m3, reranking con Haiku y top 5 | Semanas 8 y 9 |
| Contenido no textual | Tablas PDF con pdfplumber, acta y remisión escaneadas con OCR de Haiku, descripciones de imágenes con Haiku | Actividades 3, 4 y 5 |
| Respaldo | Si la ruta es sql y la consulta da error, 0 filas o la NLQ se abstiene (`NO_SQL`), también se consultan los documentos | Actividad 6 + este análisis |
| Respuesta | Haiku 5.5 medium, solo con el contexto, cita `[SQL]` (consulta ejecutada y filas) y `[D1]`..`[D5]` (pasaje o tabla de documento) | |
| Juez | Sonnet 5.5 low contra la referencia (filas de la SQL de referencia, pasajes literales o respuesta esperada) | |

Usuario de prueba: tenant `alfa`, con roles que dan acceso a todos los documentos que el golden set necesita (`datasets/permisos_semana10.json`).

Configuraciones comparadas sobre las mismas 102 preguntas:
- **integrado:** el asistente completo.
- **integrado_sin_abstencion:** igual, pero con el respaldo de la actividad 6 tal cual (sin `NO_SQL`). Mide lo que aporta la abstención.
- **solo_sql:** siempre la herramienta NLQ.
- **solo_docs:** siempre la herramienta documental.

## Métricas

- **Exactitud (juez):** Sonnet low decide si la respuesta es correcta frente a la referencia.
- **Precisión de citas de documentos:** pasajes citados `[D#]` que contienen el pasaje de referencia, sobre pasajes citados. Es una cota inferior: un pasaje citado que es pertinente pero no es el de referencia cuenta como sin evidencia.
- **Cita SQL correcta:** la respuesta cita `[SQL]` y el resultado de la consulta ejecutada coincide con el de la SQL de referencia (misma comparación de la semana 7). Solo en preguntas sql y mixtas.
- **Costo por pregunta** (sin el juez, que se reporta aparte) y **latencia p50**.

## Resultados (corrida final)

| Configuración | Tipo | Exactitud ES | Exactitud EN | Precisión de citas de documentos ES / EN | Cita SQL correcta ES / EN | Costo por pregunta (USD) | Latencia p50 (s) |
|---|---|---|---|---|---|---|---|
| **integrado** | sql | 1.000 (15/15) | 1.000 (15/15) | - | 14/15 · 15/15 | 0.00057 | 4.6 |
| | documental | 0.933 (14/15) | 1.000 (15/15) | 0.682 · 0.636 | - | 0.00077 | 5.0 |
| | no textual | 1.000 (15/15) | 1.000 (15/15) | 0.880 · 0.750 | - | 0.00090 | 5.8 |
| | mixta | 0.833 (5/6) | 0.833 (5/6) | 0.545 · 0.500 | 4/6 · 4/6 | 0.00148 | 8.2 |
| | **TOTAL** | **0.961 (49/51)** | **0.980 (50/51)** | 0.741 · 0.656 | 18/21 · 19/21 | 0.00083 | 5.3 |
| integrado_sin_abstencion | no textual | 0.800 (12/15) | 0.867 (13/15) | 0.895 · 0.792 | - | 0.00092 | 5.8 |
| | TOTAL | 0.902 (46/51) | 0.922 (47/51) | 0.691 · 0.684 | 18/21 · 19/21 | 0.00086 | 5.5 |
| solo_sql | sql | 1.000 (15/15) | 1.000 (15/15) | - | 14/15 · 15/15 | 0.00049 | 3.9 |
| | documental, no textual, mixta | 0/36 | 0/36 | - | 0/6 · 0/6 | 0.00028 | 2.5 |
| | TOTAL | 0.294 (15/51) | 0.294 (15/51) | - | 14/21 · 15/21 | 0.00034 | 2.7 |
| solo_docs | sql | 0.000 (0/15) | 0.000 (0/15) | 0.000 · 0.000 | 0/15 · 0/15 | 0.00081 | 4.8 |
| | documental | 1.000 (15/15) | 1.000 (15/15) | 0.577 · 0.652 | - | 0.00068 | 3.9 |
| | no textual | 1.000 (15/15) | 1.000 (15/15) | 0.769 · 0.909 | - | 0.00071 | 4.0 |
| | mixta | 0.167 (1/6) | 0.167 (1/6) | 0.429 · 0.412 | 0/6 · 0/6 | 0.00087 | 5.4 |
| | TOTAL | 0.608 (31/51) | 0.608 (31/51) | 0.366 · 0.416 | 0/21 · 0/21 | 0.00075 | 4.4 |

Costo y latencia combinan ES y EN; por idioma, en la salida completa del script y en `asistente_detalle.csv` (una fila por pregunta y configuración). Respaldo a documentos activado: integrado 11 de 102 preguntas; integrado_sin_abstencion 3 de 102.

## Lectura

- **El asistente integrado supera a cada herramienta por separado:** 0.961 ES y 0.980 EN, frente a 0.294 de solo_sql y 0.608 de solo_docs. Cada herramienta sola resuelve su tipo de pregunta y falla en los demás. En las mixtas, ninguna herramienta sola pasa de 1/6, mientras que el integrado llega a 5/6.
- **El integrado no pierde exactitud en el tipo propio de cada herramienta:** en sql empata con solo_sql (1.000, cita SQL 14/15 y 15/15), y en documental y no textual empata con solo_docs (salvo `int-doc-27` ES).
- **Costo:** $0.00083 por pregunta, 2.4 veces solo_sql y 1.1 veces solo_docs. Sale de 1 llamada de ruteo más 1 o 2 herramientas más la respuesta. La latencia p50 sube a 5.3 s (frente a 2.7 y 4.4 s); las mixtas son las más lentas (8.2 s), porque corren las dos herramientas en serie.
- **La abstención de la NLQ aporta en las preguntas no textuales:** pasan de 0.800/0.867 a 1.000/1.000. Sin ella, las preguntas de nivel de servicio (dato que solo está en una gráfica) se rutean a sql, y Haiku aproxima el dato con otras columnas: inventó niveles de 98 %, 99.5 % y 100 % con cita `[SQL]` (16 % en el piloto), todos falsos, y el respaldo no se activaba porque había filas. La NLQ se abstuvo en 9 de 102 preguntas del integrado (imagen, OCR y `int-doc-27`), ninguna de tipo sql.
- **El respaldo de la actividad 6 ("error o 0 filas") no basta:** una consulta que responde otra cosa devuelve filas. Esto confirma el riesgo de los 9 errores dañinos de documental a sql de la actividad 6.

## Cómo se llegó a la corrida final

| Corrida | Cambio | integrado ES / EN | Costo |
|---|---|---|---|
| Piloto (`--limite 1`, 12 preguntas × 3 configuraciones) | Diseño inicial | 0.833 / 0.833; falla `int-imagen-11` (ruteada a sql, consulta inventada con filas, sin respaldo) | $0.081 |
| Corrida 1 (102 × 4) | Abstención `NO_SQL` en la NLQ y configuración `integrado_sin_abstencion` | 0.863 / 0.922; mixtas 0/6 ES y 2/6 EN | $0.696 |
| Corrida final | La abstención aplica solo en la ruta sql (donde hay respaldo) y en solo_sql | 0.961 / 0.980 | $0.048 (solo las 16 respuestas de ruta mixta, con juez) |

En la corrida 1, la NLQ se abstuvo en 15 de las 16 preguntas de ruta mixta, porque la pregunta incluye la parte documental ("¿quién aprueba…?") y la herramienta la rechazaba completa. Era un error de alcance del cambio, no del golden set ni de las métricas. La evidencia de esa corrida queda en `asistente_cache_corrida1.json` y `asistente_detalle_corrida1.csv`; la del piloto, en `asistente_cache_prueba.json`.

**Costo total de la actividad: $0.82** (asistente $0.33 y juez $0.49), con precios oficiales de Haiku 5.5 ($0.10/$0.50) y Sonnet 5.5 ($2/$10) por MTok, revisados el 2026-10-26. El juez cuesta más que el asistente.

## Casos que fallan en el integrado

| Pregunta | Qué pasó | Tipo de falla |
|---|---|---|
| `int-mix-06` ES/EN ("¿qué SKUs críticos están en riesgo hoy y quién aprueba su compra urgente?") | La NLQ interpretó "en riesgo" como existencia bajo el punto de reorden (12 SKUs). La referencia lo define con la cobertura frente al tiempo de entrega del proveedor. La parte de quién aprueba sí es correcta (gerente de compras). | Límite del diseño: las herramientas corren en paralelo y la definición que está en el documento no llega a la consulta SQL. Requiere dos pasos (documento → SQL). |
| `int-doc-27` ES ("¿qué puede consultar el copiloto sobre existencias?") | Ruteada a sql; la NLQ se abstiene y entra el respaldo con el documento correcto. La respuesta solo dice "existencias en modo solo lectura" y omite ventas, proveedores y puntos de reorden. | Respuesta incompleta. En EN, la misma pregunta sí la acierta. |
| `int-mix-03` ES/EN (cita SQL) | El juez la da por correcta, pero la consulta devuelve proveedores con sus SKUs críticos (12 filas, 6 columnas) y la referencia solo nombres de proveedor (5 filas). | Métrica estricta: la cita SQL exige el mismo resultado. |
| `int-sql-014` ES (cita SQL) | Correcta para el juez; la consulta devuelve el id del almacén y la cantidad en lugar del nombre. | Métrica estricta (misma causa). |

**La precisión de citas de documentos** (0.66 a 0.88 en el integrado) es una cota inferior. Cuenta como sin evidencia todo pasaje citado que no contiene el pasaje de referencia, aunque sea pertinente; por ejemplo, la política de reorden citada junto a la lista de SKUs críticos. En solo_docs baja a 0.37/0.42, porque en las preguntas sql cita documentos que no responden (0 de 85 con evidencia).

## Decisión

- Asistente por defecto: **integrado con abstención en la ruta sql**. Es mejor que cada herramienta en exactitud total, iguala a cada una en su tipo y cuesta $0.00083 por pregunta.
- Pendiente para un diseño de dos pasos (fuera de alcance de esta semana): que la ruta mixta consulte primero los documentos y pase la definición a la NLQ (`int-mix-06`).
- La seguridad del asistente (cero escrituras, fuga 0 y resistencia a instrucciones inyectadas) se mide en la actividad 8.
