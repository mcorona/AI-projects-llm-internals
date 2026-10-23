"""Actividad 2: query rewriting con claude-haiku-5-5.

Compara recall@5, recall@10, nDCG@10 y MRR de la pregunta original contra la pregunta reescrita,
con el vectorial de semana 8 (bge-m3 en OpenSearch, índice semana8).
- seguimiento: la reescritura usa la pregunta previa para volver autónoma la pregunta.
- base (control): sin pregunta previa; la reescritura no debe cambiar la pregunta ni perjudicar su recall.

Salidas:
- tabla agregada en stdout;
- resultados/reescritura_detalle.csv: una fila por consulta, con acierto original y reescrito,
  tokens y costo de su llamada a Haiku, para diagnosticar casos.

Requiere LM Studio con bge-m3, OpenSearch con el índice semana8 y ANTHROPIC_API_KEY.
"""
import csv
import json
import os
import statistics
import sys
import time
from pathlib import Path

AQUI = Path(__file__).resolve().parent
RAIZ = AQUI.parents[0]
DATOS = RAIZ / "datasets"
sys.path.insert(0, str(AQUI))
sys.path.insert(0, str(RAIZ.parent / "semana-08" / "experimentos"))
from embeddings_comparacion import emb_bge  # noqa: E402
from reranking import MODELO, PRECIO, buscar_vectorial, http, metricas  # noqa: E402

SISTEMA = ("Reescribes preguntas de usuario. Si se da una pregunta previa, usa su contexto para convertir "
           "la pregunta de seguimiento en una pregunta autónoma, en el mismo idioma, sin pronombres sin referente. "
           "Si no hay pregunta previa, o la pregunta ya es autónoma, devuélvela sin cambios. "
           "Responde SOLO con la pregunta reescrita, sin comillas ni texto adicional.")


def reescribir(previa, pregunta):
    contenido = (f"Pregunta previa: {previa}\nPregunta de seguimiento: {pregunta}" if previa
                 else f"Pregunta: {pregunta}")
    r = http("POST", "https://api.anthropic.com/v1/messages", {
        "model": MODELO, "max_tokens": 300, "system": SISTEMA,
        "messages": [{"role": "user", "content": contenido}]},
        {"x-api-key": os.environ["ANTHROPIC_API_KEY"], "anthropic-version": "2023-06-01"})
    texto = "".join(b.get("text", "") for b in r["content"] if b.get("type") == "text").strip()
    return (texto or pregunta), r["usage"]["input_tokens"], r["usage"]["output_tokens"]


def promedio(filas):
    n = len(filas)
    return [sum(f[i] for f in filas) / n for i in range(3)]


def costo_llamada(tin, tout):
    return (tin * PRECIO["in"] + tout * PRECIO["out"]) / 1e6


def main():
    print(f"precio usado (prices.json, Haiku): {PRECIO}", file=sys.stderr)
    detalle = []
    print("| Tipo | Idioma | Variante | recall@5 | nDCG@10 | MRR | sin cambios | costo por consulta | latencia reescritura p50 / p95 (ms) |")
    print("|---|---|---|---|---|---|---|---|---|")
    for idioma in ("es", "en"):
        items = [json.loads(l) for l in (DATOS / f"avanzado_{idioma}.jsonl").read_text(encoding="utf-8").splitlines()]
        for tipo in ("seguimiento", "base"):
            sel = [x for x in items if x["tipo"] == tipo]
            previas = [x.get("pregunta_previa") if tipo == "seguimiento" else None for x in sel]
            reescritas, tin, tout, latencias, filas_llamada = [], 0, 0, [], []
            for x, p in zip(sel, previas):
                t0 = time.perf_counter()
                t, a, b = reescribir(p, x["question"])
                lat = (time.perf_counter() - t0) * 1000
                latencias.append(lat)
                reescritas.append(t)
                tin += a
                tout += b
                filas_llamada.append({"id": x["id"], "tipo": tipo, "idioma": idioma, "previa": p or "",
                                      "pregunta": x["question"], "reescrita": t,
                                      "tokens_in": a, "tokens_out": b,
                                      "costo_usd": f"{costo_llamada(a, b):.7f}", "latencia_ms": f"{lat:.0f}"})
            vo = emb_bge([x["question"] for x in sel], "query")[0]
            vr = emb_bge(reescritas, "query")[0]
            filas_o = [metricas(x, buscar_vectorial(v, 10)) for x, v in zip(sel, vo)]
            filas_r = [metricas(x, buscar_vectorial(v, 10)) for x, v in zip(sel, vr)]
            for fila, fo, fr in zip(filas_llamada, filas_o, filas_r):
                fila["acierto_original_r5"] = int(fo[0] > 0)
                fila["acierto_reescrita_r5"] = int(fr[0] > 0)
                detalle.append(fila)
            sin_cambio = sum(1 for x, t in zip(sel, reescritas) if t.strip() == x["question"].strip())
            costo = costo_llamada(tin, tout) / len(sel)
            for nombre, filas, cambio in (("original", filas_o, "-"), ("reescrita", filas_r, f"{sin_cambio}/{len(sel)}")):
                r5, nd, mr = promedio(filas)
                c = f"${costo:.6f}" if nombre == "reescrita" else "-"
                lat_txt = (f"{statistics.median(latencias):.0f} / {statistics.quantiles(latencias, n=20)[18]:.0f}"
                           if nombre == "reescrita" else "-")
                print(f"| {tipo} | {idioma} | {nombre} | {r5:.3f} | {nd:.3f} | {mr:.3f} | {cambio} | {c} | {lat_txt} |")

    salida = RAIZ / "resultados" / "reescritura_detalle.csv"
    salida.parent.mkdir(parents=True, exist_ok=True)
    with salida.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(detalle[0].keys()))
        w.writeheader()
        w.writerows(detalle)
    print(f"detalle por consulta: {salida}", file=sys.stderr)


if __name__ == "__main__":
    main()
