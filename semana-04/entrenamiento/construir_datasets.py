"""Construye los datasets de destilación (SFT) y DPO a partir de data/teacher.jsonl.

destilacion/train.jsonl: pregunta -> SQL del maestro, solo donde el maestro acertó.
  El sistema es el esquema SIN reglas: el alumno aprende a aplicar las reglas sin tenerlas en el prompt
  (destilación de contexto).

dpo/train.jsonl: prompt -> chosen (SQL de referencia, validado) y rejected (SQL del maestro),
  solo donde el maestro falló y su SQL es distinto de la referencia.

Uso:
    uv run python semana-04/entrenamiento/construir_datasets.py
"""
import json
from pathlib import Path

RAIZ = Path(__file__).resolve().parent
DATOS = RAIZ / "data"


def main():
    filas = [json.loads(l) for l in open(DATOS / "teacher.jsonl", encoding="utf-8")]
    reintento = DATOS / "teacher_reintento.jsonl"
    if reintento.exists():
        nuevas = {f["pregunta"]: f for f in (json.loads(l) for l in open(reintento, encoding="utf-8"))}
        filas = [nuevas.get(f["pregunta"], f) if not f["sql_maestro"] else f for f in filas]
    destilacion, dpo = [], []
    for f in filas:
        prompt = [{"role": "system", "content": f["sistema"]}, {"role": "user", "content": f["pregunta"]}]
        if f["coincide"] and f["sql_maestro"]:
            destilacion.append({"messages": prompt + [{"role": "assistant", "content": f["sql_maestro"]}]})
        if not f["coincide"] and f["sql_maestro"] and f["sql_maestro"] != f["referencia"]:
            dpo.append({
                "prompt": prompt,
                "chosen": [{"role": "assistant", "content": f["referencia"]}],
                "rejected": [{"role": "assistant", "content": f["sql_maestro"]}],
            })

    for nombre, datos in [("destilacion", destilacion), ("dpo", dpo)]:
        carpeta = RAIZ / nombre
        carpeta.mkdir(exist_ok=True)
        with open(carpeta / "train.jsonl", "w", encoding="utf-8") as fh:
            for d in datos:
                fh.write(json.dumps(d, ensure_ascii=False) + "\n")
    print(f"preguntas: {len(filas)}")
    print(f"destilación (maestro acierta): {len(destilacion)}")
    print(f"DPO (maestro falla, par válido): {len(dpo)}")


if __name__ == "__main__":
    main()
