"""Semana 12, actividad 10: resume la salida JSON de `aws ce get-cost-and-usage` (DAILY, agrupada por SERVICE)."""
import collections
import json
import sys

SEMANA = ("Bedrock", "Claude", "Cohere", "S3", "Simple Storage", "Data Automation")
d = json.load(sys.stdin)
srv, dia = collections.defaultdict(float), collections.defaultdict(float)
for r in d["ResultsByTime"]:
    for g in r["Groups"]:
        c = float(g["Metrics"]["UnblendedCost"]["Amount"])
        srv[g["Keys"][0]] += c
        dia[r["TimePeriod"]["Start"]] += c
print("| Servicio | USD | Semana 12 |\n|---|---|---|")
tot = sem = 0.0
for s, c in sorted(srv.items(), key=lambda x: -x[1]):
    if c < 1e-6:
        continue
    es = any(k in s for k in SEMANA)
    tot += c
    sem += c if es else 0
    print(f"| {s} | {c:.4f} | {'sí' if es else 'no'} |")
print(f"| **Total de la cuenta** | **{tot:.4f}** | |")
print(f"| **Servicios de la semana 12** | **{sem:.4f}** | |\n")
print("| Día | USD |\n|---|---|")
for k in sorted(dia):
    print(f"| {k} | {dia[k]:.4f} |")
print("\nDatos estimados (aún no consolidados):", "sí" if any(r.get("Estimated") for r in d["ResultsByTime"]) else "no")
