"""Construye el set de preguntas multi-salto de la actividad 7 (GraphRAG).

Cada pregunta necesita dos pasajes de referencia de dos documentos distintos. Los pasajes salen de las
preguntas base del golden set (ya validados) y se vuelven a validar como texto literal en el corpus.
Son preguntas compuestas de dos documentos; en varias la entidad puente queda implícita.
"""
import json
from pathlib import Path

R = Path(__file__).resolve().parents[2]
DS = R / "semana-09" / "datasets"
CORPUS = R / "semana-08" / "corpus"

# (id base del primer pasaje, id base del segundo, pregunta ES, pregunta EN)
PREGUNTAS = [
    ("rec-22", "rec-11",
     "¿Quién aprueba la compra urgente de un SKU en riesgo y qué factor de seguridad usa ese tipo de SKU en el punto de reorden?",
     "Who approves the urgent purchase of an at-risk SKU, and what safety factor does that type of SKU use in the reorder point?"),
    ("rec-23", "rec-14",
     "¿Desde cuántos días de cobertura se escala un SKU crítico al gerente de compras, y para cuántos días de demanda se pide ese tipo de SKU?",
     "From how many days of coverage is a critical SKU escalated to the purchasing manager, and for how many days of demand is that type of SKU ordered?"),
    ("rec-05", "rec-07",
     "¿Quién aprueba un ajuste de inventario de 15 mil pesos, y quién aprueba una orden de compra de 120 mil pesos?",
     "Who approves an inventory adjustment of 15,000 pesos, and who approves a purchase order of 120,000 pesos?"),
    ("rec-16", "rec-42",
     "¿Cuánto tarda en entregar un proveedor de China, y qué penalización se le aplica por cada semana de entrega tardía según su contrato marco?",
     "How long does a supplier from China take to deliver, and what penalty applies for each week of late delivery under its framework contract?"),
    ("rec-15", "rec-41",
     "¿Qué meta de OTIF debe cumplir un proveedor, y cuánto dura la vigencia de su contrato marco?",
     "What OTIF target must a supplier meet, and how long is its framework contract valid?"),
    ("rec-18", "rec-25",
     "¿Cuál es el horario de recepción del CEDIS de Guadalajara, y cuánto tarda en tránsito una transferencia de ese CEDIS a Monterrey?",
     "What are the receiving hours of the Guadalajara distribution center, and how long does a transfer from that center to Monterrey take in transit?"),
    ("rec-37", "rec-26",
     "¿Cuántas posiciones de tarima tiene el CEDIS de Monterrey, y cuándo se considera que un CEDIS tiene excedente para transferir?",
     "How many pallet positions does the Monterrey distribution center have, and when is a distribution center considered to have a surplus to transfer?"),
    ("rec-46", "rec-34",
     "¿Qué es una merma, y qué SKUs perecederos se revisan cada semana para evitarla?",
     "What is shrinkage, and which perishable SKUs are reviewed every week to prevent it?"),
    ("rec-36", "rec-01",
     "¿Cuánto tiene un cliente para reclamar una entrega, y cuál es el plazo para devolver el producto?",
     "How long does a customer have to file a delivery claim, and what is the deadline to return the product?"),
    ("rec-44", "rec-09",
     "Durante su primer mes, ¿qué límite de compra tiene un comprador nuevo, y cuántas cotizaciones necesita una orden mayor a 100 mil pesos?",
     "During their first month, what purchase limit does a new buyer have, and how many quotes does an order over 100,000 pesos need?"),
]

base = {lang: {d["id"]: d for d in map(json.loads, open(DS / f"avanzado_{lang}.jsonl", encoding="utf-8")) if d["tipo"] == "base"}
        for lang in ("es", "en")}
corpus = {p.name: p.read_text(encoding="utf-8") for p in CORPUS.glob("*.md")}

errores, salida = [], {"es": [], "en": []}
for i, (a, b, es, en) in enumerate(PREGUNTAS, 1):
    ga, gb = base["es"][a]["gold"][0], base["es"][b]["gold"][0]
    if ga["source"] == gb["source"]:
        errores.append(f"ms-{i:02d}: los dos pasajes son del mismo documento ({ga['source']})")
    for g in (ga, gb):
        if g["passage"] not in corpus[g["source"]]:
            errores.append(f"ms-{i:02d}: pasaje no literal en {g['source']}")
    for lang, q in (("es", es), ("en", en)):
        salida[lang].append({"id": f"ms-{i:02d}", "lang": lang, "question": q, "gold": [ga, gb], "base": [a, b]})
if errores:
    raise SystemExit("\n".join(errores))
for lang, items in salida.items():
    with open(DS / f"multisalto_{lang}.jsonl", "w", encoding="utf-8") as f:
        for x in items:
            f.write(json.dumps(x, ensure_ascii=False) + "\n")
print(f"{len(PREGUNTAS)} preguntas multi-salto por idioma; dos documentos distintos por pregunta; validación OK")
