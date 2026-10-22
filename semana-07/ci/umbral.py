"""Falla si alguna exactitud del modelo está bajo el umbral. Uso: python umbral.py 0.80"""
import json
import sys
from pathlib import Path

umbral = float(sys.argv[1])
resumenes = sorted(Path("semana-07/resultados").glob("resumen_*.json"))
if not resumenes:
    sys.exit("No hay resumen de la corrida.")
filas = json.loads(resumenes[-1].read_text(encoding="utf-8"))
for f in filas:
    print(f"{f['modelo']} {f['idioma']} exactitud={f['exactitud']}")
malas = [f for f in filas if f["exactitud"] < umbral]
if malas:
    sys.exit(f"Bajo el umbral {umbral}: " + ", ".join(f"{f['modelo']}/{f['idioma']}" for f in malas))
print(f"Todas las exactitudes >= {umbral}")
