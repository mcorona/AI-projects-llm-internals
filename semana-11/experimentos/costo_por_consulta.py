"""Semana 11, actividad 7: costo y latencia por consulta, por etapa.

Corre el pipeline decidido (recuperación adoptada + generador con el prompt solo_documentos de la actividad 6) sobre las 150
preguntas del golden set (65 respondibles y 10 sin respuesta por idioma), instrumentado por etapa:
- recuperación: embedding de la pregunta (bge-m3 local, una pregunta a la vez), búsqueda en pgvector con filtro (top 20)
  y reranking con Haiku 5.5 (el de la actividad 2); la recuperación va secuencial para que la latencia sea la de una
  consulta sola;
- generación: Haiku 5.5 medium sobre el top 5 (4 en paralelo);
- evaluación: la suite de generación por respuesta (juez Haiku 5.5 low, actividad 3): faithfulness y answer relevancy de
  RAGAS, exactitud con el juez propio y clasificación de abstención en las respondibles; solo la clasificación en las sin
  respuesta. Sin caché en disco, para que el costo sea el real; las métricas de una consulta van en serie y las consultas,
  8 en paralelo.
Tokens y USD de cada etapa salen del uso que devuelve la API (precios de semana-07/prices.json). Latencias p50 y p95 por
etapa. Al final, el costo de correr cada suite completa una vez (lo que costaría una corrida de CI), con estas cifras y
con las de las actividades 2 y 4.
Caché por consulta en resultados/costo_por_consulta_cache.json (para reanudar). Requiere NLQ_DSN, LM Studio con bge-m3 y
ANTHROPIC_API_KEY.
"""
import asyncio
import contextvars
import json
import math
import os
import re
import statistics
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))
import sensibilidad as sens  # noqa: E402

sg, sr, a = sens.sg, sens.sr, sens.a
RES = RAIZ / "resultados"
CACHE = RES / "costo_por_consulta_cache.json"
P = a.PRECIOS[f"anthropic:{a.HAIKU}"]
CUBETA = contextvars.ContextVar("cubeta")


def usd(tin, tout):
    return (tin * P["in"] + tout * P["out"]) / 1e6


def pct(v, q):
    v = sorted(v)
    return v[min(len(v) - 1, max(0, math.ceil(q * len(v)) - 1))]


def recuperar(items, cache, guardar):
    import psycopg
    conn = psycopg.connect(os.environ["NLQ_DSN"], autocommit=True)
    conn.execute("SET hnsw.ef_search = 100")
    conn.execute("SET hnsw.iterative_scan = strict_order")
    a.emb_bge(["calentamiento"], "query")
    for x in items:
        k = f"rec::{x['id']}::{x['lang']}"
        if k in cache:
            continue
        t0 = time.perf_counter()
        v, _ = a.emb_bge([x["question"]], "query")
        t1 = time.perf_counter()
        cands = conn.execute("SELECT source, content FROM semana10.chunks WHERE tenant_id = %s AND roles && %s::text[] "
                             "ORDER BY embedding <=> %s::vector LIMIT %s",
                             (sr.USUARIO["tenant"], sr.USUARIO["roles"], "[" + ",".join(map(str, v[0])) + "]", sr.CANDIDATOS)).fetchall()
        t2 = time.perf_counter()
        cands = [tuple(c) for c in cands]
        orden, tin, tout = a.llamar_haiku(x["question"], cands)
        t3 = time.perf_counter()
        ordenados = list(dict.fromkeys(orden or [])) + [i for i in range(len(cands)) if i not in (orden or [])]
        cache[k] = {"top5": [list(cands[i]) for i in ordenados[:5]], "lat_embedding": t1 - t0, "lat_busqueda": t2 - t1,
                    "lat_rerank": t3 - t2, "rerank_in": tin, "rerank_out": tout}
        guardar()


def generar(items, cache, guardar):
    from anthropic import Anthropic
    cli = Anthropic(max_retries=4, timeout=180)

    def uno(x):
        k = f"gen::{x['id']}::{x['lang']}"
        if k in cache:
            return
        chunks = [tuple(c) for c in cache[f"rec::{x['id']}::{x['lang']}"]["top5"]]
        t0 = time.perf_counter()
        r = cli.messages.create(model=a.HAIKU, max_tokens=4000, system=sens.SIS_SOLO_DOCUMENTOS,
                                extra_body={"output_config": {"effort": "medium"}},
                                messages=[{"role": "user", "content": f"Pregunta: {x['question']}\n\nContexto:\n"
                                                                      f"{a.contexto(None, {'chunks': chunks})}"}])
        cache[k] = {"respuesta": "".join(b.text for b in r.content if getattr(b, "type", "") == "text"),
                    "lat": time.perf_counter() - t0, "in": r.usage.input_tokens, "out": r.usage.output_tokens}
        guardar()
    with ThreadPoolExecutor(4) as ex:
        list(ex.map(uno, items))


async def evaluar(items, cache, guardar):
    from anthropic import AsyncAnthropic
    from openai import AsyncOpenAI
    from ragas.embeddings.base import embedding_factory
    from ragas.llms import llm_factory
    from ragas.metrics.collections import AnswerRelevancy, Faithfulness

    cliente = AsyncAnthropic(max_retries=4, timeout=180)
    crear = cliente.messages.create

    async def crear_contando(*args, **kw):
        r = await crear(*args, **kw)
        c = CUBETA.get(None)
        if c is not None:
            c["in"] += r.usage.input_tokens
            c["out"] += r.usage.output_tokens
            c["llamadas"] += 1
        return r
    cliente.messages.create = crear_contando
    juez = llm_factory(a.HAIKU, provider="anthropic", client=cliente, max_tokens=4000,
                       extra_body={"output_config": {"effort": "low"}})  # sin caché: costo real
    juez.model_args["max_retries"] = 3
    juez.model_args.pop("temperature", None)
    juez.model_args.pop("top_p", None)
    emb = embedding_factory("openai", model=os.getenv("LMSTUDIO_EMBED_MODEL", "text-embedding-bge-m3"),
                            client=AsyncOpenAI(base_url=os.getenv("LMSTUDIO_BASE_URL", "http://localhost:1234/v1"), api_key="lm-studio"))
    faith, relev = Faithfulness(llm=juez), AnswerRelevancy(llm=juez, embeddings=emb)
    sem = asyncio.Semaphore(8)

    async def json_juez(sistema, contenido):
        r = await cliente.messages.create(model=a.HAIKU, max_tokens=2000, system=sistema,
                                          extra_body={"output_config": {"effort": "low"}},
                                          messages=[{"role": "user", "content": contenido}])
        return "".join(b.text for b in r.content if getattr(b, "type", "") == "text")

    async def uno(x):
        k = f"ev::{x['id']}::{x['lang']}"
        if k in cache:
            return
        resp = cache[f"gen::{x['id']}::{x['lang']}"]["respuesta"]
        textos = [c for _, c in cache[f"rec::{x['id']}::{x['lang']}"]["top5"]]
        async with sem:
            cub = {"in": 0, "out": 0, "llamadas": 0}
            CUBETA.set(cub)
            lat, err = {}, []
            pasos = [("clase", lambda: json_juez(sg.SIS_CLASE, f"Pregunta: {x['question']}\n\nRespuesta:\n{resp}"))]
            if x["respondible"]:
                pasos += [("faithfulness", lambda: faith.ascore(user_input=x["question"], response=resp, retrieved_contexts=textos)),
                          ("answer_relevancy", lambda: relev.ascore(user_input=x["question"], response=resp)),
                          ("exactitud", lambda: json_juez(a.SIS_JUEZ, f"Pregunta: {x['question']}\n\nReferencia correcta:\n"
                                                                      f"{x['referencia']}\n\nRespuesta del asistente:\n{resp}"))]
            for nombre, fn in pasos:
                t0 = time.perf_counter()
                try:
                    await fn()
                except Exception as e:  # noqa: BLE001
                    err.append(f"{nombre}:{type(e).__name__}")
                lat[nombre] = time.perf_counter() - t0
        cache[k] = {"in": cub["in"], "out": cub["out"], "llamadas": cub["llamadas"], "lat": lat, "errores": err}
        guardar()
    await asyncio.gather(*(uno(x) for x in items))


def main():
    items = sg.items_todos()
    cache = json.loads(CACHE.read_text(encoding="utf-8")) if CACHE.exists() else {}

    def guardar():
        CACHE.write_text(json.dumps(cache, ensure_ascii=False) + "\n", encoding="utf-8")
    recuperar(items, cache, guardar)
    generar(items, cache, guardar)
    asyncio.run(evaluar(items, cache, guardar))
    guardar()

    ids = [f"{x['id']}::{x['lang']}" for x in items]
    resp = {f"{x['id']}::{x['lang']}" for x in items if x["respondible"]}
    rec = [cache[f"rec::{k}"] for k in ids]
    gen = [cache[f"gen::{k}"] for k in ids]
    ev_r = [cache[f"ev::{k}"] for k in ids if k in resp]
    ev_s = [cache[f"ev::{k}"] for k in ids if k not in resp]

    def fila(nombre, tin, tout, lat, nota=""):
        c = [usd(i, o) for i, o in zip(tin, tout)]
        print(f"| {nombre} | {statistics.mean(tin):,.0f} | {statistics.mean(tout):,.0f} | ${statistics.mean(c):.5f} | "
              f"{pct(lat, 0.5):.2f} | {pct(lat, 0.95):.2f} | {nota} |")
        return statistics.mean(c)

    print("## Costo y latencia por consulta y etapa (150 preguntas; medias por consulta)\n")
    print("| Etapa | Tokens de entrada | Tokens de salida | USD por consulta | Latencia p50 (s) | Latencia p95 (s) | Nota |")
    print("|---|---|---|---|---|---|---|")
    cero = [0] * len(rec)
    fila("Recuperación: embedding (bge-m3)", cero, cero, [r["lat_embedding"] for r in rec], "local, sin costo de API")
    fila("Recuperación: búsqueda pgvector", cero, cero, [r["lat_busqueda"] for r in rec], "top 20 con filtro")
    c_rr = fila("Recuperación: reranking (Haiku)", [r["rerank_in"] for r in rec], [r["rerank_out"] for r in rec],
                [r["lat_rerank"] for r in rec], "20 candidatos")
    lat_rec = [r["lat_embedding"] + r["lat_busqueda"] + r["lat_rerank"] for r in rec]
    print(f"| **Recuperación total** | | | ${c_rr:.5f} | {pct(lat_rec, 0.5):.2f} | {pct(lat_rec, 0.95):.2f} | |")
    c_gen = fila("**Generación** (Haiku medium)", [g["in"] for g in gen], [g["out"] for g in gen], [g["lat"] for g in gen], "top 5, prompt solo_documentos")
    lat_q = [r + g["lat"] for r, g in zip(lat_rec, gen)]
    print(f"| **Respuesta al usuario** (recuperación + generación) | | | ${c_rr + c_gen:.5f} | {pct(lat_q, 0.5):.2f} | {pct(lat_q, 0.95):.2f} | lo que paga producción |")
    c_er = fila("Evaluación, respondible (4 métricas)", [e["in"] for e in ev_r], [e["out"] for e in ev_r],
                [sum(e["lat"].values()) for e in ev_r], f"{statistics.mean(e['llamadas'] for e in ev_r):.1f} llamadas al juez")
    c_es = fila("Evaluación, sin respuesta (abstención)", [e["in"] for e in ev_s], [e["out"] for e in ev_s],
                [sum(e["lat"].values()) for e in ev_s], "1 llamada")
    print("\n### Evaluación por métrica (respondibles, latencia)\n")
    print("| Métrica | p50 (s) | p95 (s) |")
    print("|---|---|---|")
    for m in ("faithfulness", "answer_relevancy", "exactitud", "clase"):
        v = [e["lat"][m] for e in ev_r if m in e["lat"]]
        print(f"| {m} | {pct(v, 0.5):.2f} | {pct(v, 0.95):.2f} |")

    n_r, n_s = len(ev_r), len(ev_s)
    rec2 = json.loads((RES / "suite_recuperacion_cache.json").read_text(encoding="utf-8"))
    ragas_ctx = 0.4071 / 260  # actividad 2: juez de RAGAS (context precision y recall), por consulta y configuración
    print("\n## Costo de correr cada suite una vez (una corrida de CI)\n")
    print("| Suite | Qué incluye | Costo |")
    print("|---|---|---|")
    s_rec_exacta = c_rr * n_r
    print(f"| Recuperación, métricas exactas | {n_r} consultas: embedding + búsqueda + reranking | ${s_rec_exacta:.3f} |")
    print(f"| Recuperación + RAGAS (context precision y recall) | lo anterior + juez (${ragas_ctx:.5f} por consulta, actividad 2) | "
          f"${s_rec_exacta + ragas_ctx * n_r:.3f} |")
    s_gen = c_gen * (n_r + n_s) + c_er * n_r + c_es * n_s
    print(f"| Generación | {n_r + n_s} respuestas sobre contextos fijos + evaluación | ${s_gen:.3f} |")
    print(f"| **Las dos suites, métricas exactas en recuperación** | | **${s_rec_exacta + s_gen:.3f}** |")
    print(f"| Las dos suites con RAGAS también en recuperación | | ${s_rec_exacta + ragas_ctx * n_r + s_gen:.3f} |")
    errores = sum(len(e["errores"]) for e in ev_r + ev_s)
    total = sum(usd(r["rerank_in"], r["rerank_out"]) for r in rec) + sum(usd(g["in"], g["out"]) for g in gen) + \
        sum(usd(e["in"], e["out"]) for e in ev_r + ev_s)
    print(f"\nMétricas con error del juez: {errores}. Costo de esta corrida: ${total:.4f}. "
          f"Rankings de la actividad 2 disponibles: {sum(1 for k in rec2 if k.startswith('adoptado::'))}.")


if __name__ == "__main__":
    main()
