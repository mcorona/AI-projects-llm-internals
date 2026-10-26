# Actividades 1 y 2 (semana 8): estrategias de chunking

Corrida del 2026-10-26. Scripts: `experimentos/chunking_pasajes.py` (chunks y pasajes íntegros) y `experimentos/recall_chunking.py` (recall con bge-m3 en LM Studio).
Corpus de 24 documentos; golden set de semana 8 con 50 preguntas por idioma y 50 pasajes de referencia únicos. Sin modelos generativos.
Un pasaje cuenta como recuperado si alguno de los top k chunks lo contiene íntegro.

## Resultados

| Estrategia | Chunks | Caracteres promedio | Pasajes íntegros | ES recall@5 | ES recall@10 | EN recall@5 | EN recall@10 |
|---|---|---|---|---|---|---|---|
| Ventana fija 400, solape 80 | 57 | 348 | 50/50 | **1.000** | **1.000** | **1.000** | **1.000** |
| Recursiva por párrafo, máx. 300 | 84 | 203 | 48/50 | 0.950 | 0.950 | 0.940 | 0.950 |
| Por sección (chunker de inventory-copilot) | 69 | 242 | 50/50 | 0.970 | **1.000** | 0.960 | **1.000** |

La estrategia recursiva parte dos pasajes de referencia (`recepcion_almacen.md`: rechazo parcial con diferencia mayor a 2 %; `skus_criticos.md`: SKU crítico con menos de 7 días de cobertura), así que no puede recuperarlos completos con ningún k.

## Decisión

Ventana fija 400/80 como estrategia por defecto: es la mejor o empata en todas las celdas, no parte ningún pasaje y es la más simple. Su debilidad conocida es que ignora los límites de sección, lo que puede volver menos precisas las citas.

## Limitaciones

- Las diferencias son de una a tres preguntas de 50: es una tendencia consistente, no un resultado fuerte.
- Un solo modelo de embeddings (bge-m3) y un solo tamaño por estrategia.
- Corrida determinista (embeddings locales y búsqueda exacta por similitud).
