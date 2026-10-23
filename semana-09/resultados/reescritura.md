# Actividad 2: query rewriting con claude-haiku-5-5

Vectorial de semana 8 (bge-m3, índice `semana8`, fijo 400/80). Script: `experimentos/reescritura.py`.
Dos corridas del mismo código el 2026-10-22. Detalle por consulta de la segunda: `reescritura_detalle.csv`.

## Segunda corrida

| Tipo | Idioma | Variante | recall@5 | nDCG@10 | MRR | Reescritura sin cambio | Costo por consulta (USD) | Latencia reescritura p50 / p95 (ms) |
|---|---|---|---|---|---|---|---|---|
| seguimiento | es | original | 0.933 | 0.809 | 0.747 | - | - | - |
| seguimiento | es | reescrita | 0.800 | 0.711 | 0.618 | 0/15 | 0.000040 | 872 / 3316 |
| base (control) | es | original | 1.000 | 0.904 | 0.874 | - | - | - |
| base (control) | es | reescrita | 1.000 | 0.898 | 0.861 | 49/50 | 0.000085 | 1279 / 2327 |
| seguimiento | en | original | 0.867 | 0.802 | 0.739 | - | - | - |
| seguimiento | en | reescrita | 0.933 | 0.793 | 0.727 | 0/15 | 0.000081 | 1218 / 2134 |
| base (control) | en | original | 1.000 | 0.885 | 0.845 | - | - | - |
| base (control) | en | reescrita | 1.000 | 0.885 | 0.845 | 50/50 | 0.000098 | 1509 / 2696 |

## Primera corrida (PR #19, en `main`)

| Tipo | Idioma | Variante | recall@5 | Reescritura sin cambio |
|---|---|---|---|---|
| seguimiento | es | original → reescrita | 0.933 → 0.800 | 0/15 |
| seguimiento | en | original → reescrita | 0.867 → 1.000 | 0/15 |
| base (control) | es | original → reescrita | 1.000 → 0.980 | 49/50 |
| base (control) | en | original → reescrita | 1.000 → 1.000 | 49/50 |

## Casos que cambian de acierto en la segunda corrida

- ES `seg-02`: acierta el original (1) y falla la reescritura (0). Original: "¿Y cada cuánto se cuentan los SKUs de clase A para llegar a esa meta?". Reescrita: "¿Cada cuánto se cuentan los SKUs de clase A para llegar a la meta de exactitud de inventario de cada CEDIS?".
- ES `seg-14`: acierta el original (1) y falla la reescritura (0). Original: "¿Y qué hago si me da una respuesta incorrecta?". Reescrita: "¿Qué hago si el copiloto me da una respuesta incorrecta?".
- EN `seg-02`: falla el original (0) y acierta la reescritura (1).
- EN `seg-10`: falla el original (0) y acierta la reescritura (1).
- EN `seg-14`: acierta el original (1) y falla la reescritura (0).

Las reescrituras de los casos que empeoran son fieles a la pregunta original. El cambio de acierto viene de la reformulación en el ranking vectorial, no de una reescritura incorrecta.

## Variabilidad entre corridas

Con el mismo código, entre la primera y la segunda corrida cambiaron resultados: EN seguimiento pasó de 1.000 a 0.933 y ES base de 0.980 a 1.000. Las reescrituras de Haiku no son deterministas, así que una diferencia de una o dos preguntas por idioma es ruido, no señal.

## Costo

El costo es el facturado: tokens de entrada × $0.10/M + tokens de salida × $0.50/M (precio de `semana-07/prices.json`, fuente del autor, 2026-10-21).

Diferencia observada en la segunda corrida: seguimiento ES tiene 227 tokens de entrada y 35 de salida; base ES tiene 188 de entrada y 133 de salida. El seguimiento lleva más entrada, como se espera, pero en base casi nada cambia y aun así la salida es mayor. Hipótesis: la API cobra tokens de razonamiento que no aparecen en el texto devuelto. No está confirmada. Para confirmarla hay que revisar los tipos de bloque de la respuesta de la API en una llamada.

## Conclusión

- Sin efecto demostrable en esta muestra. EN seguimiento mejora en una corrida y empeora en la otra, con diferencias de una o dos preguntas.
- ES seguimiento baja en ambas corridas (0.933 → 0.800 y 0.933 → 0.800 en la primera), pero los casos que cambian son reescrituras fieles; no es un error de reescritura.
- No se adopta la reescritura como paso por defecto.
- Para decidir de verdad: tres corridas por idioma y promediar, con el mismo golden set congelado.

## Limitaciones

- 15 preguntas de seguimiento por idioma: una pregunta mueve el recall 0.067.
- Una corrida de cada versión; la variabilidad observada es del mismo orden que el efecto.
- La línea base de seguimiento ya tiene recall alto, así que hay poco margen para mejorar.
