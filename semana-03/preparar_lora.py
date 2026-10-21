"""Semana 3: separa el entrenamiento en train y valid para mlx-lm.

- data/lora/train.jsonl: pares de entrenamiento menos la validación.
- data/lora/valid.jsonl: 10 % de pares_train, para vigilar la pérdida durante el ajuste.
- data/pares_eval.jsonl no se usa aquí: queda intacto como prueba final.
"""
import json
import random
from pathlib import Path

RAIZ = Path(__file__).resolve().parent
ORIGEN = RAIZ / "data" / "pares_train.jsonl"
DESTINO = RAIZ / "data" / "lora"
DESTINO.mkdir(parents=True, exist_ok=True)

filas = [l for l in ORIGEN.read_text(encoding="utf-8").splitlines() if l.strip()]
random.Random(42).shuffle(filas)
n_valid = round(len(filas) * 0.10)
valid, train = filas[:n_valid], filas[n_valid:]
(DESTINO / "valid.jsonl").write_text("\n".join(valid) + "\n", encoding="utf-8")
(DESTINO / "train.jsonl").write_text("\n".join(train) + "\n", encoding="utf-8")
print(f"train: {len(train)}  valid: {len(valid)}  (eval intacto: data/pares_eval.jsonl)")
