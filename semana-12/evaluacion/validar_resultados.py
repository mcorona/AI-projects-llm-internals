"""Semana 12, actividad 9: valida en cada PR que los resultados versionados estén completos y sean consistentes, sin
llamar a ninguna nube ni a ningún modelo. Sale con 1 y lista los problemas si algo no cuadra.

Por cada corrida de las suites (actividades 3 a 5): existen resumen, detalle y caché; 150 preguntas (65 respondibles por
idioma y 10 sin respuesta); los ids del detalle son los del golden de semana 11; las métricas están en [0, 1]; las
medias del resumen se recalculan desde el detalle (tolerancia 5e-4); métricas del juez sin puntaje ≤ 1 % y 0 chunks de
otro tenant. Seguridad: 56 + 40 casos por sistema, fuga 0 y control sin filtro > 0. Latencia: 100 preguntas, p50 ≤ p95.
Costos: ingesta, fijo, por consulta y equilibrio para las cinco opciones. La tabla de comparación se valida aparte
(el workflow la regenera y exige que no cambie).
"""
import csv
import json
import statistics
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
REPO = RAIZ.parent
RES = RAIZ / "resultados"
SUITES = ["propio", "bedrock_adm-pred", "bedrock_adm-fijo", "bedrock_adm-fijo-bda", "bedrock_ctl-chunks", "bedrock_adm-pred_rag",
          "bedrock_adm-fijo-bda_rag", "bedrock_ctl-chunks_rag", "vertex_vx-adm_hibrida", "vertex_vx-adm_vectorial",
          "vertex_vx-adm_semantico", "vertex_vx-ctl_hibrida", "vertex_vx-ctl_vectorial", "vertex_vx-ctl_semantico"]
MET_REC = ("recall@5", "ndcg@10", "mrr", "doc_recall@5")
MET_GEN = ("exactitud", "faithfulness", "answer_relevancy")
problemas = []


def mal(msg):
    problemas.append(msg)


def golden_ids():
    return {(json.loads(l)["id"], lang) for lang in ("es", "en")
            for l in (REPO / "semana-11" / "datasets" / f"eval_rag_{lang}.jsonl").read_text(encoding="utf-8").splitlines()}


def num(v):
    return None if v in ("", "None", None) else float(v)


def validar_suite(nombre, ids):
    rutas = {k: RES / f"{nombre}_{k}" for k in ("resumen.json", "detalle.csv", "cache.json")}
    for k, r in rutas.items():
        if not r.exists():
            return mal(f"{nombre}: falta {r.name}")
    r = json.loads(rutas["resumen.json"].read_text(encoding="utf-8"))
    filas = list(csv.DictReader(open(rutas["detalle.csv"], encoding="utf-8")))
    if r.get("preguntas") != 150 or len(filas) != 150:
        mal(f"{nombre}: {r.get('preguntas')} preguntas en el resumen y {len(filas)} en el detalle (se esperan 150)")
    if {(f["id"], f["lang"].lower()) for f in filas} != ids:
        mal(f"{nombre}: los ids del detalle no son los del golden de semana 11")
    if r.get("metricas_sin_puntaje", 0) > 5:
        mal(f"{nombre}: {r['metricas_sin_puntaje']} métricas sin puntaje (máximo 5, ≈ 1 %)")
    if r.get("chunks_fuera_del_tenant", 0):
        mal(f"{nombre}: {r['chunks_fuera_del_tenant']} consultas con chunks de otro tenant")
    for lang in ("es", "en"):
        resp = [f for f in filas if f["lang"].lower() == lang and f["respondible"] == "True"]
        sin = [f for f in filas if f["lang"].lower() == lang and f["respondible"] == "False"]
        if len(resp) != 65 or len(sin) != 10:
            mal(f"{nombre}/{lang}: {len(resp)} respondibles y {len(sin)} sin respuesta (65 y 10)")
        for bloque, metricas in (("recuperacion", MET_REC), ("generacion", MET_GEN)):
            for m in metricas:
                v = r[bloque][lang].get(m)
                if v is None or not 0 <= v <= 1:
                    mal(f"{nombre}/{lang}: {m} = {v} fuera de [0, 1]")
                    continue
                xs = [num(f[m]) for f in resp if num(f[m]) is not None]
                if xs and abs(statistics.mean(xs) - v) > 5e-4:
                    mal(f"{nombre}/{lang}: {m} del resumen {v} ≠ media del detalle {statistics.mean(xs):.4f}")
        ab = r["generacion"][lang]["abstencion_correcta"]
        if not ab.endswith("/10"):
            mal(f"{nombre}/{lang}: abstención correcta {ab} (denominador 10)")


def validar_seguridad():
    s = json.loads((RES / "seguridad_resumen.json").read_text(encoding="utf-8"))
    if s["casos"] != {"rol": 56, "tenant": 40}:
        mal(f"seguridad: casos {s['casos']} (56 y 40)")
    if s["fuga_total"] != 0:
        mal(f"seguridad: fuga total {s['fuga_total']}")
    if len(s["sistemas"]) != 7:
        mal(f"seguridad: {len(s['sistemas'])} sistemas (7)")
    for n, v in s["sistemas"].items():
        for t, esperado in (("rol", 56), ("tenant", 40)):
            if v[t]["consultas"] != esperado or v[t]["chunks_no_autorizados"]:
                mal(f"seguridad {n}/{t}: {v[t]['consultas']} consultas, {v[t]['chunks_no_autorizados']} no autorizados")
    for n, v in s["control_sin_filtro"].items():
        if not (v["rol"]["chunks_no_autorizados"] > 0 and v["tenant"]["chunks_no_autorizados"] > 0):
            mal(f"seguridad: el control {n} no detecta fuga (la prueba no sería sensible)")


def validar_latencia_costos():
    lat = json.loads((RES / "latencia_resumen.json").read_text(encoding="utf-8"))
    ops = {"propio", "propio_sin_rerank", "bedrock_ctl", "bedrock_bda_rag", "vertex_ctl_sem", "vertex_adm_sem"}
    if lat.get("preguntas") != 100 or not ops <= set(lat):
        mal(f"latencia: {lat.get('preguntas')} preguntas u opciones incompletas")
    for o in ops & set(lat):
        if lat[o]["total_p50"] > lat[o]["total_p95"]:
            mal(f"latencia {o}: p50 > p95")
    c = json.loads((RES / "costos_resumen.json").read_text(encoding="utf-8"))
    opciones = {"propio", "bedrock_ctl-chunks", "bedrock_adm-fijo-bda", "vertex_vx-ctl", "vertex_vx-adm"}
    for k in ("ingesta_usd", "fijo_mensual_usd", "variable_por_consulta_usd", "costo_mensual_usd"):
        if set(c.get(k, {})) != opciones:
            mal(f"costos: {k} no cubre las cinco opciones")
    if set(c.get("equilibrio_contra_propio_consultas_mes", {})) != opciones - {"propio"}:
        mal("costos: falta el punto de equilibrio de alguna opción")


def main():
    ids = golden_ids()
    for n in SUITES:
        validar_suite(n, ids)
    validar_seguridad()
    validar_latencia_costos()
    if problemas:
        print("Resultados con problemas:\n- " + "\n- ".join(problemas))
        sys.exit(1)
    print(f"Resultados completos y consistentes: {len(SUITES)} corridas de las suites, seguridad, latencia y costos.")


if __name__ == "__main__":
    main()
