# Actividad 5: imágenes

Corrida del 2026-10-26. Script: `experimentos/imagenes.py`. Modelo: **claude-haiku-5-5, esfuerzo `low`**.

## Imágenes

Generadas con Pillow desde las fuentes congeladas en la actividad 1 y revisadas a simple vista antes de correr (`imagenes/`):

- **`grafica_nivel_servicio.png`**: barras del nivel de servicio por CEDIS en septiembre de 2026, con el valor sobre cada barra y el nombre del CEDIS debajo (Centro 97.8 %, Occidente 95.1 %, Norte 98.6 %).
- **`plano_cedis_occidente.png`**: andenes 1 a 4 de recepción y 5 a 8 de embarque, la zona de SKUs críticos bajo el andén 2 y la zona de cuarentena dentro del pasillo 12.

En las dos, la respuesta exige **asociar** elementos por su posición: un valor con su barra o una zona con su andén o pasillo. Durante la revisión se corrigieron dos ambigüedades del dibujo antes de correr: el rótulo de la cuarentena invadía el pasillo 13, y la zona de SKUs críticos abarcaba los andenes 2 y 3.

## Usos de la imagen

- **sin imagen:** solo el corpus de texto (línea base).
- **Tesseract (spa):** OCR de la imagen.
- **Claude, descripción:** Haiku describe la imagen y extrae sus datos, una línea por dato; ese texto se indexa con el pipeline.
- **Claude, respuesta directa:** Haiku responde la pregunta mirando la imagen, sin RAG.

## Resultados

| Uso de la imagen | Hechos extraídos (etiqueta y valor en la misma línea) | ES recall@5 | EN recall@5 | ES respuesta directa | EN respuesta directa |
|---|---|---|---|---|---|
| sin imagen | 0/7 | 0/5 | 0/5 | - | - |
| Tesseract (spa) | **0/7** | 4/5 | 4/5 | - | - |
| Claude Haiku 5.5 (low), descripción | **7/7** | **5/5** | **5/5** | - | - |
| Claude Haiku 5.5 (low), respuesta directa | - | - | - | **5/5** | **5/5** |

**Costo de Claude:** $0.00295 en 12 llamadas (2 descripciones y 10 respuestas directas), con 18,944 tokens de entrada y 2,099 de salida. Latencia media de 1.8 s.

Detalle: `imagenes_detalle.csv`. Extracciones: `imagenes_extracciones/`.

## Lectura

- **Tesseract lee los rótulos, pero no las relaciones.** En la gráfica, mezcla los valores con las marcas del eje ("08% 7 97.8%"), pone los tres nombres de CEDIS en una línea aparte y **no leyó "98.6%"**. En el plano, lista los rótulos por filas ("Andén 1 … Andén 8", "Zona de SKUs" / "críticos", "Pasillo 10 … Pasillo 14"), sin decir qué zona está junto a qué andén o en qué pasillo. Asoció 0 de 7 hechos.
- **El recall@5 de 4/5 sobrestima a Tesseract.** La métrica cuenta como acierto un chunk que contiene la cifra o el rótulo de la respuesta, aunque esté desconectado de su etiqueta. La única falla es la pregunta del CEDIS Norte, porque "98.6%" no se leyó. Por eso esta actividad mide también los hechos asociados.
- **Haiku extrae los 7 hechos con su relación** ("CEDIS Occidente: 95.1%", "Zona de SKUs críticos: … debajo del Andén 2", "Zona de cuarentena: … del Pasillo 12"), y su descripción recupera las 10 preguntas.
- **La respuesta directa también acierta 10 de 10.** En inglés copió los rótulos tal como aparecen en la imagen ("Pasillo 12", "Andén 2"), como pide el prompt.

## Decisión

**Imágenes con datos (gráficas, planos, diagramas): Haiku 5.5 `low` describe y extrae los datos al indexar**, a entre $0.0003 y $0.0006 por imagen (media de $0.00047 en esta corrida). La descripción entra al mismo índice que el resto del corpus, así que el asistente puede recuperarla y citarla. Tesseract no sirve para imágenes cuyo significado depende de la posición. La respuesta directa sobre la imagen es igual de exacta, pero exige saber de antemano qué imagen mirar; en el asistente, la imagen se encuentra por su descripción indexada.

## Limitaciones

- Dos imágenes sintéticas, limpias y con rótulos legibles. No hay fotos, escaneos de diagramas ni gráficas sin valores rotulados (donde habría que estimar el valor por la altura de la barra).
- 5 preguntas por idioma y 7 hechos.
- La métrica de hechos busca la etiqueta y el valor en una misma línea: es una aproximación a "asociación correcta", no una verificación semántica.
- Una corrida, con un solo modelo y esfuerzo.
