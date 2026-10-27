# Actividad 6: ruteo de preguntas

Corrida del 2026-10-26. Script: `experimentos/ruteo.py`. Modelo: **claude-haiku-5-5, esfuerzo `low`**.

## Diseño

- **Preguntas:** golden set integrado, 51 por idioma (`datasets/integrado_{es,en}.jsonl`).
- **Etiqueta correcta**, derivada del tipo congelado en la actividad 1: `sql` (15 por idioma), `documental` (15 documentales de texto y 15 no textuales de PDF, escaneo o imagen) y `mixta` (6).
- **Clasificadores:**
  - **Mayoritaria:** siempre `documental`. Es el piso: 30/51 = 0.588.
  - **Haiku 5.5 (`low`):** recibe la descripción de las dos herramientas (qué hay en la base de datos y qué hay en los documentos) y devuelve JSON con la ruta.

## Resultados

| Clasificador | Idioma | Exactitud | SQL | Documental (texto) | Documental (no textual) | Mixta |
|---|---|---|---|---|---|---|
| Mayoritaria (siempre documental) | ES | 0.588 (30/51) | 0/15 | 15/15 | 15/15 | 0/6 |
| Mayoritaria (siempre documental) | EN | 0.588 (30/51) | 0/15 | 15/15 | 15/15 | 0/6 |
| Haiku 5.5 (low) | ES | **0.882** (45/51) | **15/15** | 14/15 | 10/15 | **6/6** |
| Haiku 5.5 (low) | EN | **0.863** (44/51) | **15/15** | 14/15 | 9/15 | **6/6** |

### Matriz de confusión de Haiku (ambos idiomas)

| Esperado \ Predicho | sql | documental | mixta | formato inválido |
|---|---|---|---|---|
| sql | **30** | 0 | 0 | 0 |
| documental | 9 | **47** | 4 | 0 |
| mixta | 0 | 0 | **12** | 0 |

**Costo y latencia:** $0.00891 por 102 preguntas ($0.000087 por pregunta). Latencia p50 de 0.96 s; 65 tokens de salida en promedio; ninguna salida truncada ni con formato inválido.

Detalle: `ruteo_detalle_claude-haiku-5-5_low.csv`. Respuestas del modelo: `ruteo_claude-haiku-5-5_low.json`.

## Errores

| Pregunta | Tipo | Idioma | Predicho | Efecto |
|---|---|---|---|---|
| `int-doc-27` "¿Qué puede consultar el copiloto sobre existencias?" | documental | ES, EN | sql | dañino |
| `int-pdf-04` tiempo de entrega pactado de Shenzhen Industrial Parts | PDF | ES, EN | sql | dañino (ver nota) |
| `int-pdf-05` proveedor de Seguridad con clasificación C | PDF | ES, EN | mixta | benigno |
| `int-imagen-11` nivel de servicio más bajo | imagen | ES, EN | sql | dañino |
| `int-imagen-12` nivel de servicio del CEDIS Norte | imagen | ES / EN | mixta / sql | benigno / dañino |
| `int-imagen-13` nivel de servicio del CEDIS Centro | imagen | ES / EN | sql / mixta | dañino / benigno |
| `int-ocr-07` diferencia valorizada del acta del CEDIS Norte | escaneo | EN | sql | dañino |

- **Documental → mixta (4 casos): benigno.** La ruta mixta también consulta los documentos, así que la respuesta sigue al alcance; solo cuesta una consulta de más.
- **Documental → SQL (9 casos): dañino.** El asistente buscaría en la base de datos algo que solo está en un documento.
- **Nota sobre `int-pdf-04`:** la base sí tiene tiempos de entrega por proveedor, pero no ese proveedor, que solo existe en la matriz en PDF. Es la inconsistencia del mundo sintético anotada en la actividad 1 (los nombres de proveedores del PDF no coinciden con los de la base). Desde la redacción, rutearla a SQL es razonable.

## Lectura

- **SQL y mixtas se rutean perfecto** (30/30 y 12/12). Ninguna mixta se pierde hacia una sola fuente, que es el error más caro.
- **Los errores se concentran en las preguntas no textuales** (19/30 correctas). Su redacción suena a dato de base de datos (niveles de servicio, tiempos de entrega, diferencias de inventario), aunque el dato solo esté en una gráfica, una tabla o un acta. El clasificador no sabe qué cifras existen en la base y cuáles solo en documentos.
- **Errores dañinos:** 9 de 102 (8.8 %). Errores totales: 13 de 102.
- **Costo y latencia despreciables** frente a una respuesta completa: menos de una décima de centavo y menos de un segundo por pregunta.

## Decisión para el asistente (actividad 7)

Usar el clasificador de Haiku `low` **con respaldo**: si la ruta SQL devuelve un error o cero filas, consultar también los documentos. Eso convierte los errores documental → SQL en una consulta extra en lugar de una respuesta perdida. Ese mecanismo no se probó aquí; se mide en la actividad 7.

## Limitaciones

- 51 preguntas por idioma, con solo 6 mixtas.
- La descripción de la herramienta documental menciona los tipos de documento que existen (tablas en PDF, actas escaneadas, gráficas y planos). Es lo que sabría un asistente real sobre sus fuentes, pero facilita el ruteo de las preguntas no textuales.
- La inconsistencia de nombres de proveedores entre la base y la matriz en PDF afecta a una pregunta.
- Una corrida, con un solo modelo y esfuerzo.
