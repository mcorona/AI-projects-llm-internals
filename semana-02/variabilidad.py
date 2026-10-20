"""Semana 2: cuánto varía la respuesta según temperature y top_p.

Modelo local en LM Studio (servidor compatible con OpenAI).
Uso:  python variabilidad.py [N]        (N por defecto = 20)

Para cada valor se piden N respuestas al mismo prompt.
Variabilidad de una respuesta i = 1 - promedio de Jaccard(i, j) contra las demás.
Variabilidad del valor = promedio de esas N cifras (0 = todas idénticas).
Con las N cifras por respuesta se calculan desviación estándar, error estándar
e intervalo de confianza al 95 % (aprox. normal).
"""
import csv
import os
import re
import statistics
import sys

import matplotlib.pyplot as plt
from openai import OpenAI

BASE_URL = "http://localhost:1234/v1"
MODEL = "qwen3.8-27b-mlx@4bit"
PROMPT = "Explica en tres frases qué es el punto de reorden de un SKU y cuándo conviene revisarlo."
N = int(sys.argv[1]) if len(sys.argv) > 1 else 20
MAX_TOKENS = 600                 # margen para el razonamiento interno del modelo
TEMPERATURES = [0.0, 0.7, 1.0]   # barrido con top_p = 1.0
TOP_PS = [0.5, 0.9, 1.0]         # barrido con temperature = 1.0

DIR = os.path.dirname(os.path.abspath(__file__))
client = OpenAI(base_url=BASE_URL, api_key="lm-studio")


def responder(temperature, top_p):
    r = client.chat.completions.create(
        model=MODEL,
        messages=[{"role": "user", "content": PROMPT}],
        temperature=temperature,
        top_p=top_p,
        max_tokens=MAX_TOKENS,
    )
    texto = r.choices[0].message.content or ""
    # Quita el bloque de razonamiento <think>...</think> si el modelo lo emite
    return re.sub(r"<think>.*?</think>", "", texto, flags=re.S).strip()


def jaccard(a, b):
    A, B = set(a.lower().split()), set(b.lower().split())
    return len(A & B) / len(A | B) if A | B else 1.0


def cifras_por_respuesta(respuestas):
    """Una cifra por respuesta: 1 - Jaccard promedio contra las otras."""
    n = len(respuestas)
    return [
        1 - statistics.mean(jaccard(respuestas[i], respuestas[j])
                            for j in range(n) if j != i)
        for i in range(n)
    ]


def estadisticas(cifras):
    n = len(cifras)
    media = statistics.mean(cifras)
    desv = statistics.stdev(cifras) if n > 1 else 0.0
    ee = desv / n ** 0.5
    return media, desv, media - 1.96 * ee, media + 1.96 * ee


barridos = {
    "temperature": [(v, dict(temperature=v, top_p=1.0)) for v in TEMPERATURES],
    "top_p": [(v, dict(temperature=1.0, top_p=v)) for v in TOP_PS],
}

filas, resumen = [], []

for nombre, casos in barridos.items():
    for valor, params in casos:
        respuestas = [responder(**params) for _ in range(N)]
        for i, texto in enumerate(respuestas, 1):
            filas.append((nombre, valor, i, texto))
        cifras = cifras_por_respuesta(respuestas)
        media, desv, ic_inf, ic_sup = estadisticas(cifras)
        resumen.append((nombre, valor, N, media, desv, ic_inf, ic_sup))
        print(f"{nombre}={valor}: variabilidad {media:.3f} "
              f"(desv {desv:.3f}, IC95 [{ic_inf:.3f}, {ic_sup:.3f}], N={N})")

with open(os.path.join(DIR, "variabilidad_respuestas.csv"), "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f)
    w.writerow(["barrido", "valor", "corrida", "respuesta"])
    w.writerows(filas)

with open(os.path.join(DIR, "variabilidad_resumen.csv"), "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f)
    w.writerow(["barrido", "valor", "n", "variabilidad", "desv_estandar", "ic95_inf", "ic95_sup"])
    w.writerows(resumen)

fig, ejes = plt.subplots(1, 2, figsize=(10, 4))
for ax, nombre in zip(ejes, barridos):
    filas_b = [r for r in resumen if r[0] == nombre]
    xs = [r[1] for r in filas_b]
    ys = [r[3] for r in filas_b]
    err = [[r[3] - r[5] for r in filas_b], [r[6] - r[3] for r in filas_b]]
    ax.errorbar(xs, ys, yerr=err, marker="o", capsize=4)
    ax.set_title(f"Variabilidad vs {nombre} (Qwen local, N={N})")
    ax.set_xlabel(nombre)
    ax.set_ylabel("1 - similitud Jaccard")
    ax.set_ylim(0, 1)
    ax.grid(alpha=0.3)
fig.tight_layout()
fig.savefig(os.path.join(DIR, "variabilidad.png"), dpi=150)
print(f"gráfica y CSV guardados en {DIR}")
