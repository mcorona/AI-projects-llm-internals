# Revisión manual de referencias (muestra de 20, semilla 11)

Criterio: la referencia responde la pregunta, usa solo el pasaje (o la línea del documento que lo contiene) y no agrega ni cambia datos.

Revisión: Claude (sesión de la semana 11), 2026-10-27, contra el pasaje y el documento fuente. **20/20 correctas**; 2 agregan un dato de la misma línea de la fuente, verificado, y 1 es solo la cifra.

| # | Id | Idioma | Pregunta | Pasaje o respuesta exacta | Referencia | Veredicto |
|---|---|---|---|---|---|---|
| 1 | int-ocr-08 | es | ¿Quién fue la responsable del inventario físico del CEDIS Norte? | Laura Méndez | Laura Méndez, jefa de almacén, fue la responsable del inventario físico del CEDIS Norte. || Correcta. Agrega "jefa de almacén", que está en la misma línea del acta (`Responsable: Laura Méndez, jefa de almacén`). |
| 2 | int-ocr-10 | es | ¿Cuántas piezas se remitieron en la nota R-4471? | 120 piezas | 120 piezas || Correcta, pero es solo la cifra, sin oración completa. Se acepta: el juez compara contenido, no estilo. |
| 3 | rec-29 | es | ¿Qué debo hacer si el copiloto da una respuesta incorrecta? | Reportar respuestas incorrectas al equipo de datos con la pregunta exacta y la fecha. | Debes reportarla al equipo de datos, indicando la pregunta exacta y la fecha. || Correcta. |
| 4 | rec-33 | es | ¿Cuánto tiempo se conservan los videos de vigilancia? | Los videos de vigilancia se conservan **45 días** naturales. | Los videos de vigilancia se conservan **45 días** naturales. || Correcta. |
| 5 | int-pdf-05 | es | ¿Qué proveedor de la categoría Seguridad tiene clasificación C? | Seguridad Andina | Seguridad Andina es el proveedor de la categoría Seguridad con clasificación C. || Correcta. |
| 6 | rec-38 | es | ¿Cuál es el nivel de servicio objetivo? | El nivel de servicio objetivo es de **97%** de pedidos completos. | El nivel de servicio objetivo es de **97%** de pedidos completos. || Correcta. |
| 7 | rec-13 | es | ¿Sobre qué stock se evalúa el punto de reorden? | se evalúa sobre el **stock total**, es decir, la suma de las existencias de los tres CEDIS. | El punto de reorden se evalúa sobre el stock total, es decir, la suma de las existencias de los tres CEDIS. || Correcta. |
| 8 | rec-12 | es | ¿Cada cuánto se revisa la categoría Empaque? | la categoría Empaque se revisa **semanalmente** (los lunes) | La categoría Empaque se revisa semanalmente, los lunes. || Correcta. |
| 9 | int-pdf-02 | es | ¿Qué recargo tiene el flete exprés sobre la tarifa normal? | 35% | El recargo por flete exprés es del 35% sobre la tarifa normal. || Correcta. |
| 10 | int-imagen-12 | es | ¿Qué nivel de servicio tuvo el CEDIS Norte en septiembre de 2026? | 98.6% | El CEDIS Norte tuvo un nivel de servicio de 98.6% en septiembre de 2026. || Correcta. |
| 11 | int-imagen-11 | en | What was the lowest service level among the distribution centers in September 2026? | 95.1% | The lowest service level in September 2026 was 95.1%, at CEDIS Occidente. || Correcta. Agrega "at CEDIS Occidente", que está en la gráfica (`CEDIS Occidente: 95.1%`). |
| 12 | rec-24 | en | What is the minimum quantity for a transfer between distribution centers? | Cantidad mínima por transferencia: **20 unidades** o una tarima completa, lo que sea menor. | The minimum quantity per transfer is 20 units or one full pallet, whichever is smaller. || Correcta. |
| 13 | rec-07 | en | Who approves a purchase order of 120,000 pesos? | De $50,000 a $250,000 MXN \| Gerente de compras | The purchase order of 120,000 MXN falls in the $50,000 to $250,000 MXN range, so it must be approved by the purchasing manager (Gerente de compras). || Correcta (en v1 era una negativa: leyó la fila de tabla como rango salarial). |
| 14 | rec-29 | en | What should I do if the copilot gives a wrong answer? | Reportar respuestas incorrectas al equipo de datos con la pregunta exacta y la fecha. | You should report the incorrect answer to the data team, including the exact question and the date. || Correcta. |
| 15 | rec-20 | en | What happens if the receiving difference is 3%? | Diferencia mayor a 2%: se hace un **rechazo parcial** de la diferencia y se notifica al proveedor. | If the receiving difference is greater than 2%, a partial rejection of the difference is made and the supplier is notified. || Correcta. Aplica la regla (>2%) sin repetir el 3% de la pregunta. |
| 16 | rec-10 | en | How is the reorder point calculated? | punto de reorden = demanda diaria promedio × tiempo de entrega del proveedor (días) × factor de seguridad | The reorder point is calculated as: average daily demand × supplier lead time (days) × safety factor. || Correcta. |
| 17 | rec-06 | en | How often are class A SKUs counted? | **A:** SKUs críticos y el 20% de SKUs con mayor valor de inventario. Conteo **mensual**. | Class A SKUs are counted monthly. || Correcta. |
| 18 | rec-35 | en | What is the maximum height of a pallet? | La altura máxima de una tarima es de **1.20 metros**. | The maximum height of a pallet is 1.20 metres. || Correcta. |
| 19 | int-pdf-02 | en | What surcharge does express freight have over the standard rate? | 35% | The express freight surcharge is 35% over the standard rate. || Correcta. |
| 20 | rec-45 | en | What is safety stock? | **Stock de seguridad:** existencia adicional para cubrir variaciones de demanda o de entrega. | Safety stock is additional inventory held to cover variations in demand or delivery. || Correcta. |
