"""Semana 11, actividad 8: eval de RAG en CI, con dos suites separadas (un job de GitHub Actions por suite).

--suite recuperacion (no llama al modelo de respuesta):
  índice semana10.chunks (30 documentos, chunking fijo 400/80) reconstruido en el pgvector de servicio, usuario del tenant
  alfa con todos los roles y filtro dentro de la consulta; top 20 por similitud y reranking con Haiku 5.5 (pipeline
  adoptado). Métricas exactas sobre las 65 respondibles por idioma: recall@3, recall@5, MRR, nDCG@10 y AP@5 (actividad 2).
  Sin RAGAS en esta suite: context precision equivale a AP@5 con juez (Pearson 0.84, actividad 2) y cuesta 4 veces más
  (actividad 7).
--suite generacion (no depende del buscador):
  contextos fijos de resultados/contextos_generacion.json (actividad 4), generador Haiku 5.5 medium con el prompt
  solo_documentos (actividad 6), juez Haiku 5.5 low (actividad 3). Las 150 preguntas completas, sin subconjunto: la
  corrida cuesta ≈ $0.22 (actividad 7). Métricas por idioma: faithfulness y answer relevancy (RAGAS 0.4.3), exactitud
  (juez propio), precisión de citas, no abstención falsa en las 65 respondibles y abstención correcta en las 10 sin
  respuesta.

Embeddings en CI: text-embedding-3-small (OpenAI), como en semanas 8 a 10 (bge-m3 corre en LM Studio, no en Actions);
afecta al índice de recuperación y a answer relevancy. Por eso los umbrales se calibran con la primera corrida de CI y no
con los valores locales.

Regla de calibración (semana 10, fijada antes de la primera corrida): umbral = múltiplo de 0.05 inmediatamente inferior a
(valor de la primera corrida - max(0.03, 1/n)), con n preguntas por idioma (65 respondibles; 10 sin respuesta). Con
--calibrar no se aplican umbrales: se imprimen los valores y el umbral que resulta.
Métricas del juez sin puntaje (error de API tras los reintentos): se toleran hasta el 1 % de las llamadas de la corrida y
se excluyen de las medias; por encima, el job falla.

--local: prueba de humo en la Mac (bge-m3 de LM Studio e índice semana10.chunks ya construido). --limite N: N respondibles
y 1 sin respuesta por idioma.
Requiere ANTHROPIC_API_KEY; recuperación: PG_ADMIN_DSN y NLQ_DSN (copilot_ro); sin --local, OPENAI_API_KEY.
"""
import argparse
import asyncio
import json
import math
import os
import statistics
import sys
import time
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "experimentos"))
import sensibilidad as sens  # noqa: E402  (importa las suites de las actividades 2 y 4 y el asistente de semana 10)

sg, sr, a = sens.sg, sens.sr, sens.a
MODELO_EMB = "text-embedding-3-small"
MET_REC = ("recall@3", "recall@5", "mrr", "ndcg@10", "ap@5")
MET_GEN = ("faithfulness", "answer_relevancy", "exactitud", "precision_citas", "no_abstencion_falsa", "abstencion_correcta")
# Umbrales por suite, métrica e idioma, calibrados con la primera corrida de CI (ver resultados/ci_calibracion.md).
UMBRALES = None
MAX_SIN_PUNTAJE = 0.01
PRECIO = a.PRECIOS[f"anthropic:{a.HAIKU}"]


def embed_openai(textos, tipo=None):
    out = []
    for i in range(0, len(textos), 100):
        req = Request("https://api.openai.com/v1/embeddings",
                      data=json.dumps({"model": MODELO_EMB, "input": textos[i:i + 100]}).encode("utf-8"),
                      headers={"Content-Type": "application/json", "Authorization": f"Bearer {os.environ['OPENAI_API_KEY']}"})
        for intento in range(4):
            try:
                with urlopen(req, timeout=120) as r:
                    datos = json.loads(r.read())["data"]
                break
            except HTTPError as e:
                if e.code not in (429, 500, 502, 503, 504) or intento == 3:
                    raise
                time.sleep(2 ** (intento + 1))
        out += [d["embedding"] for d in sorted(datos, key=lambda d: d["index"])]
    return out, None


def umbral_de(valor, n):
    return math.floor(round((valor - max(0.03, 1 / n)) / 0.05, 6)) * 0.05


def golden(limite):
    items = sg.items_todos()
    if not limite:
        return items
    sel = []
    for lang in ("es", "en"):
        sel += [x for x in items if x["lang"] == lang and x["respondible"]][:limite]
        sel += [x for x in items if x["lang"] == lang and not x["respondible"]][:1]
    return sel


def suite_recuperacion(items, local):
    if not local:
        a.emb_bge = embed_openai  # el asistente (índice) y la suite de recuperación usan a.emb_bge
        a.indexar()
    resp = [x for x in items if x["respondible"]]
    cache = {}
    sr.recuperar(resp, cache)
    valores = {m: {"es": [], "en": []} for m in MET_REC}
    for x in resp:
        m = sr.metricas([tuple(c) for c in cache[f"adoptado::{x['id']}::{x['lang']}"]["ranking"]], x["gold"])
        for k in MET_REC:
            valores[k][x["lang"]].append(m[k])
    costo = sum(v["costo"] for k, v in cache.items() if k.startswith("adoptado::"))
    fallos = sum(1 for k, v in cache.items() if k.startswith("adoptado::") and v.get("rerank_fallo"))
    info = {"consultas": len(resp), "reranking_fallido": fallos}
    return {m: {l: (statistics.mean(v), len(v)) for l, v in por.items() if v} for m, por in valores.items()}, costo, info, []


def suite_generacion(items, local):
    if not local:  # answer relevancy de RAGAS con los embeddings de OpenAI
        os.environ["LMSTUDIO_BASE_URL"] = "https://api.openai.com/v1"
        os.environ["LMSTUDIO_EMBED_MODEL"] = MODELO_EMB
        os.environ["EMB_API_KEY"] = os.environ["OPENAI_API_KEY"]
    ctx = json.loads(sg.CONTEXTOS.read_text(encoding="utf-8"))
    cache = {}

    def guardar():
        pass
    sg.generar(items, ctx, cache, guardar, sistema=sens.SIS_SOLO_DOCUMENTOS)
    uso = asyncio.run(sg.evaluar(items, ctx, cache, guardar))
    res = {m: {} for m in MET_GEN}
    for lang in ("es", "en"):
        r = [x for x in items if x["lang"] == lang and x["respondible"]]
        s = [x for x in items if x["lang"] == lang and not x["respondible"]]
        k = lambda x: f"{x['id']}::{x['lang']}"  # noqa: E731
        for m in ("faithfulness", "answer_relevancy", "exactitud"):
            v = [cache[f"{m}::{k(x)}"]["valor"] for x in r if cache[f"{m}::{k(x)}"]["valor"] is not None]
            if v:
                res[m][lang] = (statistics.mean(v), len(r))
        nc = nb = 0
        for x in r:
            c, b = sg.citas(cache[f"gen::{k(x)}"]["respuesta"], ctx[k(x)]["chunks"], x["gold"])
            nc, nb = nc + c, nb + b
        if r:
            res["precision_citas"][lang] = (nb / nc if nc else 0.0, len(r))
            res["no_abstencion_falsa"][lang] = (1 - sum(cache[f"clase::{k(x)}"]["valor"] == "abstiene" for x in r) / len(r), len(r))
        if s:
            res["abstencion_correcta"][lang] = (sum(cache[f"clase::{k(x)}"]["valor"] == "abstiene" for x in s) / len(s), len(s))
    metricas_juez = [v for kk, v in cache.items() if not kk.startswith("gen::")]
    sin = sum(1 for v in metricas_juez if v.get("valor") is None)
    costo_gen = sum(v["costo"] for kk, v in cache.items() if kk.startswith("gen::"))
    costo_ev = (uso["in"] * PRECIO["in"] + uso["out"] * PRECIO["out"]) / 1e6
    info = {"respuestas": len(items), "llamadas_juez": uso["llamadas"], "metricas_sin_puntaje": sin,
            "costo_generacion": round(costo_gen, 4), "costo_evaluacion": round(costo_ev, 4)}
    fallas = []
    if sin > MAX_SIN_PUNTAJE * len(metricas_juez):
        fallas.append(f"{sin}/{len(metricas_juez)} métricas del juez sin puntaje (máximo {MAX_SIN_PUNTAJE:.0%})")
    return res, costo_gen + costo_ev, info, fallas


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--suite", choices=("recuperacion", "generacion"), required=True)
    ap.add_argument("--calibrar", action="store_true", help="primera corrida: imprime valores y umbrales, sin aplicarlos")
    ap.add_argument("--local", action="store_true", help="prueba de humo con bge-m3 local y el índice existente")
    ap.add_argument("--limite", type=int, default=0, help="N respondibles y 1 sin respuesta por idioma (prueba de humo)")
    args = ap.parse_args()
    aplicar = not (args.calibrar or args.local or args.limite)
    if aplicar and (UMBRALES is None or args.suite not in UMBRALES):
        raise SystemExit("Sin umbrales calibrados: corre con --calibrar y fija UMBRALES con la regla de la docstring.")
    t0 = time.time()
    items = golden(args.limite)
    correr = suite_recuperacion if args.suite == "recuperacion" else suite_generacion
    valores, costo, info, fallas = correr(items, args.local)

    lineas = [f"## Suite de {args.suite}", "", "| Métrica | Idioma | Valor | n | Umbral |", "|---|---|---|---|---|"]
    calibrados = {}
    for m, por_lang in valores.items():
        for lang in ("es", "en"):
            if lang not in por_lang:
                continue
            v, n = por_lang[lang]
            u = UMBRALES[args.suite][m][lang] if aplicar else umbral_de(v, n)
            calibrados.setdefault(m, {})[lang] = round(u, 2)
            nota = "" if aplicar else " (calibrado)"
            lineas.append(f"| {m} | {lang} | {v:.3f} | {n} | {u:.2f}{nota} |")
            if aplicar and v < u - 1e-9:
                fallas.append(f"{m}/{lang}: {v:.3f} < {u:.2f}")
    lineas += ["", "Información: " + json.dumps(info, ensure_ascii=False),
               f"Costo Anthropic de la corrida: ${costo:.4f}; duración {time.time() - t0:.0f} s"]
    if not aplicar:
        lineas += ["", f'UMBRALES["{args.suite}"] = ' + json.dumps(calibrados)]
    texto = "\n".join(lineas)
    print(texto)
    if os.getenv("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a", encoding="utf-8") as fh:
            fh.write(texto + "\n")
    if fallas:
        raise SystemExit("FALLA:\n- " + "\n- ".join(fallas))
    print("Todos los checks pasaron." if aplicar else "Sin umbrales aplicados (calibración o prueba de humo).")


if __name__ == "__main__":
    main()
