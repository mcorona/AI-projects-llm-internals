# Actividad 2: text-to-SQL sobre esquema legado

Corrida del 2026-10-26. Script: `experimentos/sql_legado.py`. Modelo: **claude-sonnet-5-5, esfuerzo `medium`** ($2 / $10 por millón de tokens, página oficial de precios de Anthropic consultada el 2026-10-26).
Set: el difícil de semana 7 (`semana-07/datasets/nlq_hard_validado.jsonl`), 43 preguntas por idioma. Exactitud por ejecución con el mismo comparador de semana 7 (`semana-07/run_eval.py`) y el rol de solo lectura `copilot_ro`.

## Esquema legado

`legado/legado.sql` crea el esquema `legado` con vistas de nombres crípticos sobre las tablas de inventory-copilot. Los datos y los valores son los mismos; solo cambian los nombres (`products` → `artmst`, `stock.on_hand` → `exidet.exi_qty`, `sales_daily` → `vtadia`, etc.). Así, el SQL de referencia de semana 7, sobre las tablas originales, sigue siendo el resultado esperado. En las variantes legado, el SQL generado corre con `search_path = legado`, de modo que el modelo solo puede usar las vistas crípticas. Diccionario de datos: `legado/diccionario.json` (6 tablas, 26 columnas, en español, con valores de ejemplo).

## Variantes

- **copilot:** esquema original (`semana-07/schema.sql`), control con el mismo modelo.
- **legado:** DDL legado sin diccionario.
- **legado_dic:** DDL legado más el diccionario completo.
- **legado_rec:** DDL y diccionario solo de las 3 tablas más afines a la pregunta (bge-m3); k = 3 fijado antes de correr.

## Resultados

| Variante | Idioma | Exactitud | Correctas | Resultado distinto | No es SELECT | Recuperación completa de tablas | Costo por pregunta (USD) | Latencia p50 (s) | Tokens de salida (media) |
|---|---|---|---|---|---|---|---|---|---|
| copilot | ES | 0.953 | 41/43 | 2 | 0 | - | 0.00298 | 1.7 | 120 |
| copilot | EN | 0.977 | 42/43 | 1 | 0 | - | 0.00298 | 1.8 | 122 |
| legado | ES | 0.977 | 42/43 | 1 | 0 | - | 0.00268 | 1.6 | 164 |
| legado | EN | 0.953 | 41/43 | 2 | 0 | - | 0.00248 | 1.5 | 147 |
| legado_dic | ES | 0.953 | 41/43 | 2 | 0 | - | 0.00433 | 1.8 | 131 |
| legado_dic | EN | 0.977 | 42/43 | 1 | 0 | - | 0.00429 | 1.7 | 129 |
| legado_rec | ES | 0.744 | 32/43 | 9 | 2 | 33/43 | 0.00348 | 1.7 | 176 |
| legado_rec | EN | 0.721 | 31/43 | 10 | 2 | 31/43 | 0.00347 | 1.7 | 180 |

Sin errores de SQL ni salidas truncadas. Detalle por pregunta: `sql_legado_detalle_claude-sonnet-5-5_medium.csv`.

**Costo:** $1.1475 en 344 llamadas. Además: piloto de 24 llamadas, $0.0914 (`sql_legado_detalle_claude-sonnet-5-5_medium_prueba.csv`), y un primer intento que se detuvo cuando se agotó el saldo de la cuenta de la API, con unas 43 llamadas cobradas (~$0.16, estimado; no se guardaron sus resultados).

## Comparación con semana 7

En el mismo set y con el esquema original, semana 7 midió claude-haiku-5-5: ES 41/43 (0.953) y EN 43/43 (1.000), con un costo de $0.0040 a $0.0057 por idioma (unos $0.0001 por pregunta). Sonnet 5.5 en la variante `copilot` sacó ES 0.953 y EN 0.977, a $0.0030 por pregunta: **la misma exactitud dentro del ruido, a entre 22 y 32 veces el costo por pregunta**. Por eso se corrió también Haiku 5.5 en las cuatro variantes (sección siguiente).

## Haiku 5.5 (corrida adicional)

Mismas cuatro variantes con **claude-haiku-5-5, esfuerzo `medium`** ($0.10 / $0.50 por millón, prompts de hasta 100K tokens). Costo: **$0.0923** en 344 llamadas. Detalle: `sql_legado_detalle_claude-haiku-5-5_medium.csv`.

| Variante | Idioma | Haiku: exactitud | Sonnet: exactitud | Haiku: costo por pregunta (USD) | Sonnet: costo por pregunta (USD) | Haiku: latencia p50 (s) |
|---|---|---|---|---|---|---|
| copilot | ES | 0.977 (42/43) | 0.953 | 0.00021 | 0.00298 | 1.7 |
| copilot | EN | 1.000 (43/43) | 0.977 | 0.00018 | 0.00298 | 1.6 |
| legado | ES | 0.884 (38/43) | 0.977 | 0.00028 | 0.00268 | 2.1 |
| legado | EN | 0.953 (41/43) | 0.953 | 0.00025 | 0.00248 | 2.1 |
| legado_dic | ES | **0.977 (42/43)** | 0.953 | **0.00033** | 0.00433 | 2.0 |
| legado_dic | EN | **1.000 (43/43)** | 0.977 | **0.00032** | 0.00429 | 2.0 |
| legado_rec | ES | 0.767 (33/43) | 0.744 | 0.00029 | 0.00348 | 2.1 |
| legado_rec | EN | 0.721 (31/43) | 0.721 | 0.00029 | 0.00347 | 2.1 |

- **Sin diccionario, Haiku falla por los valores, no por los nombres.** Entiende la estructura legado, pero escribe `'ALEMANIA'` o `'China'` donde la base guarda códigos ISO (`'DE'`, `'CN'`), y busca la ciudad en `alm_dsc` ("CEDIS Norte") en lugar de `alm_cdd`. Son 7 fallos de 86 en `legado`.
- **El diccionario corrige exactamente eso:** trae el formato de los valores (códigos de país, ciudades) y qué columna guarda cada dato. Con él, Haiku iguala o supera a Sonnet en las cuatro celdas comparables.
- **La recuperación del diccionario falla igual que con Sonnet y por la misma causa:** 63 de 64 correctas con las tablas completas, 1 de 22 sin ellas. Las 14 salidas que no son SELECT son todas de `legado_rec`: negativas ante tablas faltantes.

## Lectura

- **Los nombres crípticos no afectaron a Sonnet:** `legado` saca lo mismo que `copilot` (una pregunta de diferencia, en direcciones opuestas por idioma). En un esquema de 6 tablas, con nombres como `artmst` o `exi_qty` y llaves que se pueden inferir, el DDL basta.
- **El diccionario completo no mejoró la exactitud** y subió el costo por pregunta frente a `legado` (62 % en ES y 73 % en EN), por el prompt más largo.
- **El diccionario recuperado bajó la exactitud a 0.72–0.74, y la causa es la recuperación, no el SQL:** con todas las tablas necesarias recuperadas, 63 de 64 correctas; con alguna faltante, 0 de 22. La tabla que más faltó fue `artmst`, el maestro de artículos (17 de 22), y luego `almmst` (5). La búsqueda por similitud prioriza las tablas que la pregunta menciona (ventas, existencias) y deja fuera el maestro que se necesita para el JOIN.
- **Cuando faltó una tabla, Sonnet no inventó nombres:** las 4 salidas que no fueron SELECT son negativas explícitas ("artmst no está disponible"). Es el comportamiento correcto ante un esquema incompleto.

## Decisión

**Haiku 5.5 con el DDL legado y el diccionario completo** para el text-to-SQL del asistente: 0.977 ES y 1.000 EN, a $0.00033 por pregunta, unas 13 veces menos que Sonnet con el diccionario ($0.0043) y con igual o mejor exactitud. El diccionario es necesario con Haiku (aporta el formato de los valores), aunque Sonnet no lo necesitó.

La recuperación del diccionario solo se justifica en esquemas grandes, y tendría que ampliar las tablas recuperadas con sus tablas relacionadas por llave foránea (por ejemplo, agregar siempre el maestro `artmst` cuando se recupera `exidet` o `vtadia`). Esa variante no se probó.

## Limitaciones

- Una corrida por variante; 43 preguntas por idioma, así que una pregunta mueve la exactitud 0.023.
- Esquema pequeño (6 tablas) y con nombres crípticos pero adivinables. Un esquema legado real, con cientos de tablas y abreviaturas sin patrón, haría más necesario el diccionario.
- Dos modelos (Sonnet 5.5 y Haiku 5.5), ambos con esfuerzo `medium`; una corrida de cada uno.
- k = 3 fijo en la recuperación; no se probaron otros valores ni recuperación por columnas.
