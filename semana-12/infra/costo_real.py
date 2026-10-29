"""Semana 12, actividad 10: resume `aws ce get-cost-and-usage` (DAILY, agrupado por SERVICE y RECORD_TYPE).

El costo de la semana es el USO BRUTO (RECORD_TYPE = Usage): si la cuenta tiene créditos promocionales, estos aparecen
como registros Credit negativos y el neto puede salir en $0 aunque sí hubo consumo.
"""
import collections
import json
import sys

SEMANA = ("Bedrock", "Claude", "Cohere", "S3", "Simple Storage", "Data Automation")
d = json.load(sys.stdin)
uso, tipo, dia = collections.defaultdict(float), collections.defaultdict(float), collections.defaultdict(float)
for r in d["ResultsByTime"]:
    for g in r["Groups"]:
        servicio, registro = g["Keys"]
        c = float(g["Metrics"]["UnblendedCost"]["Amount"])
        tipo[registro] += c
        if registro == "Usage":
            uso[servicio] += c
            dia[r["TimePeriod"]["Start"]] += c
print("Uso bruto por servicio (antes de créditos)\n\n| Servicio | USD | Semana 12 |\n|---|---|---|")
tot = sem = 0.0
for s, c in sorted(uso.items(), key=lambda x: -x[1]):
    if abs(c) < 1e-6:
        continue
    es = any(k in s for k in SEMANA)
    tot += c
    sem += c if es else 0
    print(f"| {s} | {c:.4f} | {'sí' if es else 'no'} |")
print(f"| **Uso bruto de la cuenta** | **{tot:.4f}** | |")
print(f"| **Uso bruto de servicios de la semana 12** | **{sem:.4f}** | |\n")
print("Neto por tipo de registro\n\n| Tipo | USD |\n|---|---|")
for k, c in sorted(tipo.items()):
    print(f"| {k} | {c:.4f} |")
print(f"| **Neto a pagar** | **{sum(tipo.values()):.4f}** |\n")
print("| Día | Uso bruto USD |\n|---|---|")
for k in sorted(dia):
    print(f"| {k} | {dia[k]:.4f} |")
print("\nDatos estimados (aún no consolidados):", "sí" if any(r.get("Estimated") for r in d["ResultsByTime"]) else "no")
