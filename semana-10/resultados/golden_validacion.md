# Actividad 1: validación del golden set integrado

Fecha: 2026-10-26. Script: `datasets/construir_integrado.py`. Archivos: `datasets/integrado_{es,en}.jsonl` y `fuentes/`.

## Composición (por idioma)

| Tipo | Preguntas | Referencia | Origen |
|---|---|---|---|
| SQL | 15 | SQL esperado, exactitud por ejecución (`order_matters` del set original) | `semana-07/datasets/nlq_hard_validado.jsonl` |
| Documental | 15 | Pasaje literal | Preguntas base de `semana-09/datasets/avanzado_*.jsonl` |
| No textual: PDF con tablas | 5 | Respuesta exacta en la fuente | `fuentes/tarifas_flete.md`, `fuentes/matriz_proveedores.md` |
| No textual: OCR | 5 | Respuesta exacta en la fuente | `fuentes/acta_inventario_norte.md`, `fuentes/remision_r4471.md` |
| No textual: imagen | 5 | Respuesta exacta en la fuente | `fuentes/grafica_nivel_servicio.json`, `fuentes/plano_cedis_occidente.json` |
| Mixta | 6 | SQL esperado + pasaje literal | SQL nuevo + corpus de semana 8 |

Total: 51 por idioma. Las preguntas EN son traducciones de las ES con la misma referencia.

## Validaciones

- **Pasajes literales:** los de las preguntas documentales y mixtas aparecen tal cual en el corpus de semana 8.
- **Fuentes no textuales:** cada respuesta está en su fuente y **no** aparece en el corpus de texto. Si apareciera, la pregunta podría responderse sin leer el PDF, el escaneo o la imagen. Esta regla rechazó una primera versión de una pregunta de imagen (respuesta "Occidente", que ya está en el corpus); se cambió por el valor de la gráfica (95.1%).
- **SQL (42 consultas, 15 SQL y 6 mixtas por idioma):** ejecutadas contra la base de inventory-copilot con su rol de lectura (`PG_DSN`). Todas se ejecutan y devuelven al menos una fila sin nulos.

Resultados de las mixtas en la validación:

| Mixta | Resultado SQL |
|---|---|
| `int-mix-01` SKUs críticos | 30 |
| `int-mix-02` unidades vendidas en septiembre de 2026 | 75,001 |
| `int-mix-03` proveedores con más de 20 días de entrega | Shenzhen Components, Ningbo Hardware, Rhein Industrietechnik, … |
| `int-mix-04` existencias en Monterrey | 49,382 |
| `int-mix-05` productos de la categoría Seguridad | 25 |
| `int-mix-06` SKUs críticos en riesgo hoy (ejemplo del plan) | SKU-0164, SKU-0009, SKU-0189, … |

`int-mix-06` usa la definición de riesgo de `skus_criticos.md`: días de cobertura (stock total ÷ venta diaria promedio de los últimos 30 días) menores que el tiempo de entrega del proveedor.

## Limitaciones

- Los nombres de proveedores de la matriz en PDF (por ejemplo, Shenzhen Industrial Parts) no coinciden con los de la base (por ejemplo, Shenzhen Components). Son mundos sintéticos separados; ninguna pregunta cruza la matriz con la base, pero un asistente podría confundirlos si alguna lo hiciera.
- Los resultados SQL dependen de los datos sintéticos actuales de inventory-copilot (semilla 42). Si se regeneran con otra semilla, las respuestas esperadas cambian, aunque las consultas siguen siendo válidas.
