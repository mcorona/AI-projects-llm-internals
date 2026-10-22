# Semana 4 · Destilación y DPO (práctica extra)

Ajustar un modelo pequeño con respuestas de uno grande (destilación) y con preferencias entre respuestas (DPO), usando el mismo esquema legado y la misma evaluación de la semana 3.

## Diseño

- **Maestro:** Qwen3.8-27B con las reglas de negocio en el prompt. Es el mejor método medido en la semana 3 (50.0 % de coincidencia).
- **Alumno:** Qwen2.5-Coder-7B, sin reglas en el prompt.
- **Datos de entrenamiento:** solo `semana-03/data/lora/train.jsonl` (157 preguntas). La evaluación (`pares_eval.jsonl`, 46 pares) no entra a ningún paso.

Esto prueba la destilación de contexto: si el alumno aprende a aplicar las reglas sin tenerlas en el prompt.

## Pasos

1. `generar_teacher.py`: el maestro responde las 157 preguntas de entrenamiento. Se ejecuta y se compara con la referencia. Salida: `data/teacher.jsonl`.
2. `construir_datasets.py`: arma dos datasets desde `teacher.jsonl`:
   - `destilacion/train.jsonl`: pregunta -> SQL del maestro, solo donde acertó. Sistema sin reglas.
   - `dpo/train.jsonl`: prompt -> `chosen` (SQL de referencia) y `rejected` (SQL del maestro), solo donde falló.
3. Entrenamiento:
   - Destilación: LoRA con mlx-lm sobre `destilacion/`, igual que en la semana 3.
   - DPO: pendiente de confirmar el formato que acepta `mlx-lm` en la versión instalada.
4. Evaluación: el alumno destilado y el alumno DPO se corren con `evaluar_sql.py` sobre `pares_eval.jsonl`, y se comparan con el 7B base y el 27B con reglas usando `estadistica.py`.

## Cómo correrlo

Requiere LM Studio con el 27B cargado y `LB_READER_DSN` en el entorno (el mismo `.env` de LegacyBridge que usaste en la semana 3).

```bash
cd ~/AI-projects-llm-internals
set -a; source ~/legacybridge-v2/.env; set +a
caffeinate -i uv run python semana-04/entrenamiento/generar_teacher.py
uv run python semana-04/entrenamiento/construir_datasets.py
```

El primer comando tarda varias horas: 157 preguntas, con razonamiento del 27B de hasta 8192 tokens cada una.

## Resultados

Mismos 46 pares de evaluación de la semana 3 (sin reglas en el prompt).

| Método | Ejecuta | Coincide en resultado [IC 95 %] |
|---|---|---|
| 7B base | 80.4 % | 37.0 % [24.5, 51.4] |
| 7B + LoRA v1 (semana 3) | 84.8 % | 37.0 % [24.5, 51.4] |
| 7B + destilación (checkpoint 150) | 84.8 % | 37.0 % [24.5, 51.4] |
| 27B + reglas en prompt (maestro) | 69.6 % | 50.0 % [36.1, 63.9] |

- Destilación contra 7B base: los mismos 46 casos aciertan, McNemar p = 1.000. El adaptador sí cambia el SQL en 14 de 46 respuestas, pero ninguno cambia el resultado correcto.
- El alumno no aprendió las reglas que el maestro sí aplica. Con 95 ejemplos de entrenamiento, el adaptador aprende el formato, igual que el LoRA v1.

Problemas de la corrida:

- Divergencia numérica: la pérdida dio `nan` en la iteración 280 con lr 5e-6, y en la 60 con lr 1e-5. Usamos el checkpoint 150, antes de cualquier `nan`.
- 9 de 49 preguntas difíciles quedaron sin SQL del maestro, así que el alumno no vio esos casos.
- DPO no se entrenó: la versión instalada de `mlx-lm` no tiene modo DPO en el CLI.

Decisión: no se usa el adaptador de destilación. La regla de la semana 3 se mantiene: si el prompt basta, no se ajusta.

## Decisión sobre DPO

**No se entrena DPO en esta semana.** Motivo: el CLI instalado de `mlx_lm.lora` no tiene modo DPO, y escribir un ciclo de entrenamiento propio queda fuera del alcance de la semana.

- Lo que sí queda hecho: el dataset de preferencias `dpo/train.jsonl` (42 pares, `chosen` = SQL de referencia, `rejected` = SQL del maestro donde falló).
- Lo que falta para usarlo: un framework con DPO (por ejemplo, TRL de Hugging Face) corriendo sobre GPU o en un entorno con soporte. Queda como trabajo futuro.
- Esta decisión no cambia la conclusión de la semana: con 46 pares de evaluación, el ajuste supervisado tampoco mejoró el resultado, así que no hay evidencia para priorizar DPO.
