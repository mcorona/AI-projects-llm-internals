"""Intervalos de Wilson (95 %) y prueba exacta de McNemar pareada para las corridas de semana 3.

Uso:
    uv run python semana-03/estadistica.py base7b lora7b base
    uv run python semana-03/estadistica.py base7b lora7b --comparar base7b lora7b
    --metrica ejecuta   para comparar ejecución en vez de coincidencia de resultado
"""
import argparse
import json
import math
from pathlib import Path

RAIZ = Path(__file__).resolve().parent


def cargar(nombre):
    ruta = RAIZ / "resultados" / f"{nombre}_detalle.jsonl"
    return [json.loads(l) for l in open(ruta, encoding="utf-8")]


def wilson(k, n, z=1.96):
    if n == 0:
        return 0.0, 0.0
    p = k / n
    den = 1 + z * z / n
    centro = (p + z * z / (2 * n)) / den
    margen = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / den
    return centro - margen, centro + margen


def mcnemar_exacta(solo_a, solo_b):
    """p de dos colas: pares discordantes contra una binomial(n, 1/2)."""
    n = solo_a + solo_b
    if n == 0:
        return 1.0
    k = min(solo_a, solo_b)
    p = 2 * sum(math.comb(n, i) for i in range(k + 1)) / 2 ** n
    return min(1.0, p)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("corridas", nargs="*")
    ap.add_argument("--metrica", default="coincide_resultado", choices=["ejecuta", "coincide_resultado"])
    ap.add_argument("--comparar", nargs=2, metavar=("A", "B"))
    args = ap.parse_args()

    nombres = list(dict.fromkeys(args.corridas + (args.comparar or [])))
    datos = {n: cargar(n) for n in nombres}

    print(f"{'corrida':30s} {'n':>3s} {'aciertos':>8s} {'tasa':>7s}   IC 95 % (Wilson)")
    for n in args.corridas:
        filas = datos[n]
        k = sum(bool(f[args.metrica]) for f in filas)
        N = len(filas)
        lo, hi = wilson(k, N)
        print(f"{n:30s} {N:3d} {k:8d} {k / N:7.1%}   [{lo:.1%}, {hi:.1%}]")

    if args.comparar:
        a, b = args.comparar
        ma = {f["pregunta"]: bool(f[args.metrica]) for f in datos[a]}
        mb = {f["pregunta"]: bool(f[args.metrica]) for f in datos[b]}
        comunes = [q for q in ma if q in mb]
        solo_a = sum(ma[q] and not mb[q] for q in comunes)
        solo_b = sum(mb[q] and not ma[q] for q in comunes)
        p = mcnemar_exacta(solo_a, solo_b)
        print(f"\n{a} vs {b} ({args.metrica}, {len(comunes)} pares comunes)")
        print(f"  solo {a} acierta: {solo_a}   solo {b} acierta: {solo_b}   McNemar p = {p:.3f}")
        print("  diferencia significativa al 5 %" if p < 0.05 else "  diferencia no significativa al 5 %")


if __name__ == "__main__":
    main()
