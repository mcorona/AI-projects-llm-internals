# Actividad 3: PDFs con tablas

Corrida del 2026-10-26. Script: `experimentos/pdf_tablas.py`.

## PDFs

Generados con reportlab (fuente Arial Unicode, para conservar "→" y acentos) en `pdf/`:

| PDF | Origen | Tabla de referencia |
|---|---|---|
| `tarifas_flete.pdf` | `fuentes/tarifas_flete.md` (fuente congelada en la actividad 1) | 4 filas × 3 columnas |
| `matriz_proveedores.pdf` | `fuentes/matriz_proveedores.md` (fuente congelada en la actividad 1) | 5 filas × 5 columnas |
| `ordenes_de_compra.pdf` | `semana-08/corpus/ordenes_de_compra.md` (niveles de aprobación) | 4 filas × 2 columnas |
| `proveedores.pdf` | `semana-08/corpus/proveedores.md` (tiempos de entrega, en lista) | sin tabla; solo cuenta para el recall |

Total de referencia: 3 tablas, 13 filas, 45 celdas.

## Extractores

- **original (sin PDF):** el Markdown fuente; referencia superior.
- **pypdf:** texto plano de cada página.
- **pdfplumber:** tablas detectadas como filas (`celda | celda | …`) y el resto del texto aparte.
- **Claude Haiku 5.5, esfuerzo `low`:** el PDF como entrada, transcrito a Markdown. Costo: **$0.00162** por los 4 PDFs (8,148 tokens de entrada y 1,615 de salida), 2.5 s de media por PDF.

Las extracciones están en `resultados/pdf_extracciones/`.

## Resultados

### Estructura de las tablas

| Extractor | Celdas presentes | Celdas en su fila | Filas íntegras |
|---|---|---|---|
| original (sin PDF) | 45/45 (1.000) | 45/45 (1.000) | 13/13 |
| pypdf | 45/45 (1.000) | 14/45 (0.311) | **0/13** |
| pdfplumber | 45/45 (1.000) | **45/45 (1.000)** | **13/13** |
| Claude Haiku 5.5 (low) | 45/45 (1.000) | **45/45 (1.000)** | **13/13** |

### Recuperación (preguntas de PDF del golden set, 5 por idioma)

| Extractor | ES recall@5 | EN recall@5 |
|---|---|---|
| original (sin PDF) | 4/5 | 4/5 |
| pypdf | 5/5 | 5/5 |
| pdfplumber | 5/5 | 4/5 |
| Claude Haiku 5.5 (low) | 4/5 | 5/5 |

Todas las fallas son la misma pregunta, `int-pdf-05` ("¿qué proveedor de la categoría Seguridad tiene clasificación C?"). La palabra "Seguridad" atrae chunks del corpus sobre esa categoría (devoluciones, descuentos, seguridad de instalaciones), y el chunk de la matriz queda fuera del top 5 según cómo quedó cortado. Falla incluso con el texto original, así que es un problema de ranking, no de extracción.

## Lectura

- **Los tres extractores conservan el texto:** las 45 celdas aparecen en todos.
- **pypdf pierde la estructura de tabla:** deja cada celda en su propia línea (por ejemplo, "Guadalajara → Monterrey", luego "$10,900", luego "2 días"), así que ninguna fila queda íntegra. Para responder "cuánto cuesta la ruta X" hay que reconstruir qué valor va con qué ruta por el orden del texto, algo frágil en tablas anchas o de varias páginas.
- **pdfplumber y Claude conservan las 13 filas completas.** pdfplumber lo hace sin costo, localmente y de forma determinista; Claude cuesta unos $0.0004 por página y tarda unos 2.5 s.
- **El recall@5 no distingue a los extractores en este set:** las respuestas son celdas sueltas que aparecen en el chunk aunque la fila esté rota, y la única diferencia es una pregunta de ranking. El efecto de la estructura en la respuesta final se mide en la actividad 7, con el asistente.

## Decisión

**pdfplumber** como extractor por defecto para PDFs digitales con tablas: misma estructura que Claude, sin costo ni llamadas externas. Claude queda para lo que pdfplumber no cubre: PDFs escaneados (actividad 4) o tablas con celdas combinadas y estructuras complejas. pypdf no se usa para documentos con tablas.

## Limitaciones

- PDFs generados con reportlab, limpios y de una página, con tablas de cuadrícula simple. PDFs reales (celdas combinadas, tablas sin bordes, varias páginas) son más difíciles para pdfplumber.
- 5 preguntas por idioma: una pregunta mueve el recall 0.2.
- pdfplumber agrega las tablas al final del texto de la página, no en su posición original, lo que puede separar una tabla de su encabezado en el chunking.
- Una corrida de Claude, con un solo modelo y esfuerzo.
