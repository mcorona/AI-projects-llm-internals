"""Semana 12: suites de la semana 11 sobre un sistema de recuperación cualquiera, con el mismo golden y el mismo generador.

Cada opción de la semana (pipeline propio, Bedrock Knowledge Bases, Vertex AI Search) entra como un backend de
recuperación que devuelve, por pregunta, el ranking [(source, content), ...] con la latencia y el costo de recuperar.
Todo lo demás es común y no cambia entre opciones:
- golden: semana-11/datasets/eval_rag_{es,en}.jsonl (75 por idioma: 65 respondibles, 10 sin respuesta), usuario del tenant
  alfa con todos los roles;
- suite de recuperación (65 respondibles por idioma): recall@1/3/5/10, MRR, nDCG@10 y AP@5 con relevancia exacta (un
  chunk del documento de referencia que contiene el pasaje literal; semana 11, actividad 2), más doc_recall@5 (el
  documento de referencia está en el top 5), que no depende de dónde corte cada servicio sus chunks;
- suite de generación sobre lo recuperado (las 150 preguntas): top 5 al generador común (Haiku 5.5 medium, prompt
  solo_documentos de semana 11), juez Haiku 5.5 low: exactitud (juez propio), faithfulness y answer relevancy (RAGAS),
  precisión y cobertura de citas, abstención correcta y falsa, y atribución de cada falla a recuperación o generación
  (semana 11, actividad 5);
- costo y latencia por consulta de recuperación y de generación.
Caché por backend en resultados/<backend>_cache.json (reanuda); resumen en resultados/<backend>_resumen.json y detalle en
resultados/<backend>_detalle.csv. Backends: propio (este archivo); los administrados se agregan en las actividades 4 y 5.
"""
import argparse
import asyncio
import csv
import datetime as dt
import json
import math
import os
import statistics
import sys
import time
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
REPO = RAIZ.parent
sys.path.insert(0, str(REPO / "semana-11" / "experimentos"))
import sensibilidad as sens  # noqa: E402  (suites de recuperación y generación de semana 11 y el asistente de semana 10)

sg, sr, a = sens.sg, sens.sr, sens.a
RES = RAIZ / "resultados"
K_GEN = 5
P = a.PRECIOS[f"anthropic:{a.HAIKU}"]
MET_REC = ("recall@1", "recall@3", "recall@5", "recall@10", "mrr", "ndcg@10", "ap@5", "doc_recall@5")


def pct(v, q):
    v = sorted(v)
    return v[min(len(v) - 1, max(0, math.ceil(q * len(v)) - 1))] if v else float("nan")


# ---------- backends de recuperación ----------

def recuperar_propio(items, guardar_uno):
    """Pipeline propio (semanas 8 a 11): bge-m3 en LM Studio, pgvector semana10.chunks con filtro de tenant y roles dentro
    de la consulta, top 20 y reranking con Haiku 5.5 (configuración `adoptado` de semana 11)."""
    import psycopg
    with psycopg.connect(os.environ["NLQ_DSN"]) as c:
        n, tenants = c.execute("SELECT count(*), array_agg(DISTINCT tenant_id) FROM semana10.chunks").fetchone()
    if n != 68 or tenants != ["alfa"]:
        raise SystemExit(f"semana10.chunks tiene {n} chunks de {tenants}; se esperaban 68 de alfa (índice de semana 10, act. 7)")
    local = {}
    sr.recuperar(items, local)
    for x in items:
        r = local[f"adoptado::{x['id']}::{x['lang']}"]
        guardar_uno(x, {"ranking": r["ranking"], "latencia_s": r["latencia_s"], "costo": r["costo"],
                        "rerank_fallo": r.get("rerank_fallo", False)})


BACKENDS = {"propio": recuperar_propio}


# ---------- métricas ----------

def metricas_recuperacion(x, ranking):
    m = sr.metricas([tuple(c) for c in ranking], x["gold"])
    fuentes = {Path(g["source"]).stem for g in x["gold"]}
    m["doc_recall@5"] = len(fuentes & {s for s, _ in ranking[:5]}) / len(fuentes)
    return {k: m[k] for k in MET_REC}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--backend", choices=sorted(BACKENDS), default="propio")
    ap.add_argument("--limite", type=int, default=0, help="N preguntas por idioma y tipo (prueba de humo)")
    args = ap.parse_args()
    items = sg.items_todos()
    if args.limite:
        items = [x for lang in ("es", "en") for resp in (True, False)
                 for x in [y for y in items if y["lang"] == lang and y["respondible"] == resp][:args.limite]]
    nombre = args.backend + (f"_humo{args.limite}" if args.limite else "")
    ruta = RES / f"{nombre}_cache.json"
    cache = json.loads(ruta.read_text(encoding="utf-8")) if ruta.exists() else {}

    def guardar():
        ruta.write_text(json.dumps(cache, ensure_ascii=False) + "\n", encoding="utf-8")

    def guardar_uno(x, r):
        cache[f"rec::{x['id']}::{x['lang']}"] = r
    t0 = time.time()
    faltan = [x for x in items if f"rec::{x['id']}::{x['lang']}" not in cache]
    if faltan:
        BACKENDS[args.backend](faltan, guardar_uno)
        guardar()
    ctx = {f"{x['id']}::{x['lang']}": {"chunks": cache[f"rec::{x['id']}::{x['lang']}"]["ranking"][:K_GEN]} for x in items}
    sg.generar(items, ctx, cache, guardar, sistema=sens.SIS_SOLO_DOCUMENTOS)
    uso = asyncio.run(sg.evaluar(items, ctx, cache, guardar))
    guardar()

    filas = []
    for x in items:
        k = f"{x['id']}::{x['lang']}"
        rec, gen = cache[f"rec::{k}"], cache[f"gen::{k}"]
        f = {"id": x["id"], "lang": x["lang"], "respondible": x["respondible"],
             "tipo": "sin_respuesta" if not x["respondible"] else ("no_textual" if x["tipo"].startswith("no_textual") else "base"),
             "lat_rec": rec["latencia_s"], "costo_rec": rec["costo"], "lat_gen": gen["latencia_s"], "costo_gen": gen["costo"],
             "clase": cache[f"clase::{k}"]["valor"], "respuesta": gen["respuesta"]}
        if x["respondible"]:
            f.update(metricas_recuperacion(x, rec["ranking"]))
            f.update({m: cache[f"{m}::{k}"]["valor"] for m in ("exactitud", "faithfulness", "answer_relevancy")})
            nc, nb = sg.citas(gen["respuesta"], ctx[k]["chunks"], x["gold"])
            f.update({"citas": nc, "citas_con_pasaje": nb,
                      "pasajes_en_contexto": metricas_recuperacion(x, rec["ranking"][:K_GEN])["recall@5"]})
            f["falla"] = "" if f["exactitud"] == 1 else ("recuperación" if f["pasajes_en_contexto"] < 1 else "generación")
        else:
            f["falla"] = "" if f["clase"] == "abstiene" else "generación (inventa)"
        filas.append(f)

    def media(fs, c):
        v = [r[c] for r in fs if r.get(c) is not None]
        return round(statistics.mean(v), 4) if v else None
    resumen = {"backend": args.backend, "fecha": dt.date.today().isoformat(), "preguntas": len(items),
               "generador": f"{a.HAIKU} medium, prompt solo_documentos", "juez": f"{a.HAIKU} low", "k_contexto": K_GEN,
               "recuperacion": {}, "generacion": {}, "costo_usd_por_consulta": {}, "latencia_s": {}, "fallas": []}
    for lang in ("es", "en"):
        r = [f for f in filas if f["lang"] == lang and f["respondible"]]
        s = [f for f in filas if f["lang"] == lang and not f["respondible"]]
        resumen["recuperacion"][lang] = {m: media(r, m) for m in MET_REC} | {"n": len(r)}
        nc = sum(f["citas"] for f in r)
        resumen["generacion"][lang] = {
            "n": len(r), "exactitud": media(r, "exactitud"), "faithfulness": media(r, "faithfulness"),
            "answer_relevancy": media(r, "answer_relevancy"),
            "precision_citas": round(sum(f["citas_con_pasaje"] for f in r) / nc, 4) if nc else None,
            "cobertura_cita": round(sum(1 for f in r if f["citas_con_pasaje"]) / len(r), 4) if r else None,
            "abstencion_falsa": f"{sum(f['clase'] == 'abstiene' for f in r)}/{len(r)}",
            "abstencion_correcta": f"{sum(f['clase'] == 'abstiene' for f in s)}/{len(s)}"}
    resumen["costo_usd_por_consulta"] = {"recuperacion": round(statistics.mean(f["costo_rec"] for f in filas), 6),
                                         "generacion": round(statistics.mean(f["costo_gen"] for f in filas), 6)}
    resumen["latencia_s"] = {e: {"p50": round(pct([f[c] for f in filas], 0.5), 2), "p95": round(pct([f[c] for f in filas], 0.95), 2)}
                             for e, c in (("recuperacion", "lat_rec"), ("generacion", "lat_gen"))}
    resumen["fallas"] = [{"id": f["id"], "lang": f["lang"], "atribucion": f["falla"], "respuesta": f["respuesta"][:200]}
                         for f in filas if f["falla"]]
    sin = sum(1 for kk, v in cache.items() if kk.split("::")[0] in ("faithfulness", "answer_relevancy", "exactitud", "clase")
              and v.get("valor") is None)
    resumen["metricas_sin_puntaje"] = sin
    resumen["costo_evaluacion_corrida_usd"] = round((uso["in"] * P["in"] + uso["out"] * P["out"]) / 1e6, 4)
    resumen["rerank_fallido"] = sum(1 for kk, v in cache.items() if kk.startswith("rec::") and v.get("rerank_fallo"))
    (RES / f"{nombre}_resumen.json").write_text(json.dumps(resumen, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    with (RES / f"{nombre}_detalle.csv").open("w", encoding="utf-8", newline="") as fh:
        campos = sorted({c for f in filas for c in f}, key=lambda c: (c == "respuesta", c))
        w = csv.DictWriter(fh, fieldnames=campos)
        w.writeheader()
        w.writerows(filas)

    print(f"## Backend: {args.backend} ({len(items)} preguntas)\n")
    print("### Suite de recuperación (respondibles)\n")
    print("| Idioma | n | " + " | ".join(MET_REC) + " |")
    print("|---|---|" + "---|" * len(MET_REC))
    for lang, m in resumen["recuperacion"].items():
        print(f"| {lang} | {m['n']} | " + " | ".join(f"{m[k]:.3f}" for k in MET_REC) + " |")
    print("\n### Suite de generación sobre lo recuperado (top 5, generador común)\n")
    print("| Idioma | n | exactitud | faithfulness | answer_relevancy | precisión de citas | cobertura de cita | abstención falsa | abstención correcta |")
    print("|---|---|---|---|---|---|---|---|---|")
    for lang, g in resumen["generacion"].items():
        print(f"| {lang} | {g['n']} | {g['exactitud']:.3f} | {g['faithfulness']:.3f} | {g['answer_relevancy']:.3f} | "
              f"{g['precision_citas']:.3f} | {g['cobertura_cita']:.3f} | {g['abstencion_falsa']} | {g['abstencion_correcta']} |")
    print("\n### Costo y latencia por consulta\n")
    print("| Etapa | USD por consulta | p50 (s) | p95 (s) |\n|---|---|---|---|")
    for e in ("recuperacion", "generacion"):
        print(f"| {e} | ${resumen['costo_usd_por_consulta'][e]:.5f} | {resumen['latencia_s'][e]['p50']} | {resumen['latencia_s'][e]['p95']} |")
    print(f"\nFallas ({len(resumen['fallas'])}):")
    for f in resumen["fallas"]:
        print(f"- {f['id']} {f['lang']} ({f['atribucion']}): {f['respuesta'][:140]}")
    total = sum(f["costo_rec"] for f in filas) + sum(f["costo_gen"] for f in filas) + resumen["costo_evaluacion_corrida_usd"]
    print(f"\nMétricas sin puntaje: {sin}. Reranking fallido: {resumen['rerank_fallido']}. Duración {time.time() - t0:.0f} s. "
          f"Costo (recuperación + generación de lo guardado y evaluación de esta corrida): ${total:.4f}")


if __name__ == "__main__":
    main()
