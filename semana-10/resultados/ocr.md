# Actividad 4: OCR de documentos escaneados

Corrida del 2026-10-26. Script: `experimentos/ocr.py`.

## Escaneos

5 documentos, una página cada uno, en `escaneos/`:

| Documento | Origen | Para qué |
|---|---|---|
| `acta_inventario_norte` | `fuentes/` (congelada en la actividad 1) | 3 preguntas de OCR del golden set |
| `remision_r4471` | `fuentes/` (congelada en la actividad 1) | 2 preguntas de OCR del golden set |
| `devoluciones` | corpus de semana 8 | pasajes `rec-01` a `rec-03` |
| `inventario_ciclico` | corpus de semana 8 | pasajes `rec-04` a `rec-06` |
| `recepcion_almacen` | corpus de semana 8 | pasajes `rec-18` a `rec-20` |

Proceso: Markdown → PDF (generador de la actividad 3) → imagen a 200 dpi en grises → rotación aleatoria de ±1.5°, desenfoque gaussiano (0.6), ruido gaussiano y puntos de sal y pimienta → JPEG con calidad 85. Semilla fija (20261026).

## Extractores

- **original (sin escanear):** el texto visible de la página; referencia superior.
- **Tesseract 5.5.3**, idioma español (`spa`).
- **Claude Haiku 5.5** y **Claude Sonnet 5.5**, ambos con esfuerzo `low`, con la imagen como entrada y transcripción a Markdown.

Las extracciones están en `resultados/ocr_extracciones/`.

## Resultados

### Tasa de error por carácter (CER)

| Extractor | Acta | Remisión | Devoluciones | Inventario cíclico | Recepción | **Medio** |
|---|---|---|---|---|---|---|
| original (sin escanear) | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 |
| Tesseract (spa) | 0.003 | 0.007 | 0.016 | 0.017 | 0.004 | **0.009** |
| Claude Haiku 5.5 (low) | 0.003 | 0.000 | 0.000 | 0.000 | 0.000 | **0.001** |
| Claude Sonnet 5.5 (low) | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | **0.000** |

### Recuperación (9 pasajes y 5 respuestas por idioma)

| Extractor | ES pasajes | EN pasajes | ES respuestas | EN respuestas |
|---|---|---|---|---|
| original (sin escanear) | 8/9 | 8/9 | 5/5 | 5/5 |
| Tesseract (spa) | 8/9 | 8/9 | 5/5 | 5/5 |
| Claude Haiku 5.5 (low) | 8/9 | 8/9 | 5/5 | 5/5 |
| Claude Sonnet 5.5 (low) | 8/9 | 8/9 | 5/5 | 5/5 |

El pasaje que falla es `rec-06` (clases ABC del inventario cíclico) en todos los extractores, incluido el original. Es un problema de ranking de esa pregunta, no de OCR.

### Costo y latencia de Claude

| Modelo | Tokens de entrada | Tokens de salida | Costo (5 páginas) | Costo por página | Latencia media |
|---|---|---|---|---|---|
| Haiku 5.5 (low) | 24,200 | 1,714 | $0.00328 | $0.0007 | 3.2 s |
| Sonnet 5.5 (low) | 24,200 | 1,714 | $0.06554 | $0.0131 | 4.3 s |

Cada página escaneada cuenta 4,840 tokens de entrada (la imagen más el prompt). Haiku y Sonnet transcribieron **exactamente el mismo texto** en 4 de los 5 documentos. En el acta, Haiku leyó un punto como paréntesis ("DIF)" en lugar de "DIF."); es la única diferencia. Por eso coinciden los tokens de salida.

## Lectura

- **Claude transcribe casi sin errores:** Haiku, con un solo carácter mal en 5 páginas; Sonnet, con ninguno.
- **Tesseract tiene un CER de 0.9 %, y la mayoría no afecta el contenido:** lee las viñetas "•" como "+" o "»", cambia alguna puntuación ("Ficticia," por "Ficticia;") y comete algún error de letra ("entrega" por "eritrega").
- **Con este nivel de ruido, el OCR no cambia el recall:** los 4 extractores recuperan lo mismo que el texto original, en pasajes y en respuestas. Ningún error de Tesseract cayó dentro de un pasaje o una cifra preguntada.
- **Sonnet no aporta frente a Haiku en esta tarea:** mismo texto en 4 de 5 documentos, 20 veces el costo y más latencia.

## Decisión

- **Escaneos limpios o moderados, como estos:** Tesseract. No cuesta nada, es local y no alteró ninguna cifra ni pasaje preguntado.
- **Cuando la exactitud de cifras importa o el escaneo es malo** (actas, remisiones, facturas): Claude Haiku 5.5 con esfuerzo `low`, a unos $0.0007 por página.
- **Sonnet no se usa para OCR:** cuesta 20 veces más y no mejoró a Haiku.

## Limitaciones

- Escaneos sintéticos con ruido moderado, una página por documento y fuente digital limpia. No hay manuscritos, sellos, manchas, baja resolución ni fotos tomadas con celular.
- Un documento por fuente y una sola semilla de ruido. Con más ruido, la diferencia entre Tesseract y Claude probablemente crecería; esta corrida no lo mide.
- 9 pasajes y 5 respuestas por idioma.
- El CER cuenta los errores de viñetas igual que los de contenido.
