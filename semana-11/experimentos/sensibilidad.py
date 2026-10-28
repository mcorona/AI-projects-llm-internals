"""Semana 11, actividad 6: sensibilidad de las suites a cambios del pipeline.

Línea base (pipeline adoptado): suite de recuperación = configuración `adoptado` de la actividad 2; suite de generación =
contextos fijos y respuestas de la actividad 4 (Haiku 5.5 medium con el prompt del asistente).

Cambios controlados, uno a la vez:
1. sin_rerank: quitar el reranking (vectorial + filtro en orden de similitud). Debe moverse la recuperación.
2. sin_solo_contexto: prompt del generador sin la instrucción de usar solo el contexto ni la de decir que no alcanza y no
   inventar. Debe moverse la generación (faithfulness y abstención).
3. rec300: chunking recursivo de 300 caracteres (semana 8) en lugar de fijo 400/80, sobre los mismos 30 documentos. Es un
   cambio de indexado: debe moverse la recuperación; puede mover la generación, porque cambia el texto de cada chunk.
Variante adicional (no es un cambio degradante): solo_documentos, el prompt del asistente sin la instrucción de citar
[SQL] (pendiente de la actividad 4, donde las menciones a SQL bajaron la faithfulness).

Controles de ruido (repetición sin cambios): rerank_repeticion (otro reranking de los mismos candidatos) y
gen_repeticion (otra generación con los mismos contextos y prompt). Estiman cuánto se mueve cada suite sin cambiar nada.

Una suite no ejecuta el componente del otro lado (la de recuperación no genera; la de generación usa contextos fijos), así
que el reranking no puede mover la suite de generación ni el prompt la de recuperación: se verifica que sus entradas sean
idénticas (huella de los contextos y del ranking) y no se vuelven a correr.

Criterio, fijado antes de correr: una métrica se mueve si la diferencia pareada contra la línea base tiene IC bootstrap
95 % (2,000 remuestreos, semilla 11) que excluye 0 y su magnitud supera la del control de repetición de esa suite. Una
suite se mueve si se mueve al menos una de sus métricas principales:
- recuperación: recall@3, recall@5, MRR, nDCG@10, AP@5 (relevancia exacta; RAGAS context precision sigue al AP@5,
  actividad 2, y no se recalcula aquí por costo);
- generación: exactitud, faithfulness, answer relevancy, precisión de citas (respondibles) y abstención correcta (las 20
  sin respuesta: se mueve si el conteo cambia en 2 o más y más que en la repetición).
Requiere PG_ADMIN_DSN (índice rec300), NLQ_DSN, LM Studio con bge-m3 y ANTHROPIC_API_KEY.
"""
import asyncio
import hashlib
import json
import os
import random
import statistics
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))
import suite_generacion as sg  # noqa: E402

sr, a = sg.sr, sg.a
RES = RAIZ / "resultados"
CACHE = RES / "sensibilidad_cache.json"
TABLA_REC300 = "semana11.chunks_rec300"
SIS_SIN_SOLO_CONTEXTO = ("Eres el asistente de una distribuidora industrial. Responde la pregunta en el idioma de la "
                         "pregunta, de forma breve y completa. Cita la fuente de cada dato con [D1], [D2], … cuando venga "
                         "de los pasajes.")
SIS_SOLO_DOCUMENTOS = ("Eres el asistente de una distribuidora industrial. Responde la pregunta usando SOLO el contexto dado, "
                       "en el idioma de la pregunta, de forma breve y completa. Cita la fuente de cada dato con [D1], [D2], "
                       "… Si el contexto no alcanza para responder, dilo y no inventes datos.")
MET_REC = ("recall@3", "recall@5", "mrr", "ndcg@10", "ap@5")
MET_GEN = ("exactitud", "faithfulness", "answer_relevancy", "precision_citas")


def huella(obj):
    return hashlib.sha256(json.dumps(obj, ensure_ascii=False, sort_keys=True).encode()).hexdigest()[:12]


def bootstrap(dif, n=2000, semilla=11):
    rnd = random.Random(semilla)
    medias = sorted(statistics.mean(rnd.choice(dif) for _ in dif) for _ in range(n))
    return statistics.mean(dif), medias[int(0.025 * n)], medias[int(0.975 * n) - 1]


# ---------- índice rec300 y recuperación ----------

def indexar_rec300():
    import psycopg
    trocear = a.ESTRATEGIAS["recursivo_300"]
    docs = a.documentos()
    filas = [(s, c) for s, t in docs.items() for c in trocear(t, s)]
    vecs, _ = a.emb_bge([c for _, c in filas], "doc")
    with psycopg.connect(os.environ["PG_ADMIN_DSN"], autocommit=True) as conn:
        conn.execute("CREATE SCHEMA IF NOT EXISTS semana11")
        conn.execute(f"DROP TABLE IF EXISTS {TABLA_REC300}")
        conn.execute(f"CREATE TABLE {TABLA_REC300} (id int PRIMARY KEY, tenant_id text NOT NULL, roles text[] NOT NULL, "
                     f"source text NOT NULL, content text NOT NULL, embedding vector({len(vecs[0])}) NOT NULL)")
        conn.execute(f"CREATE INDEX ON {TABLA_REC300} USING hnsw (embedding vector_cosine_ops)")
        with conn.cursor() as cur:
            for i, ((s, c), v) in enumerate(zip(filas, vecs)):
                cur.execute(f"INSERT INTO {TABLA_REC300} VALUES (%s,%s,%s,%s,%s,%s::vector)",
                            (i, "alfa", a.ROLES[s], s, c, "[" + ",".join(map(str, v)) + "]"))
        conn.execute("GRANT USAGE ON SCHEMA semana11 TO copilot_ro")
        conn.execute(f"GRANT SELECT ON {TABLA_REC300} TO copilot_ro")
    print(f"índice rec300: {len(docs)} documentos, {len(filas)} chunks", file=sys.stderr)
    return len(filas)


def recuperar_rec300(items, cache, guardar):
    import psycopg
    faltan = [x for x in items if f"rec300_base::{x['id']}::{x['lang']}" not in cache]
    if faltan:
        conn = psycopg.connect(os.environ["NLQ_DSN"], autocommit=True)
        conn.execute("SET hnsw.ef_search = 100")
        conn.execute("SET hnsw.iterative_scan = strict_order")
        vecs, _ = a.emb_bge([x["question"] for x in faltan], "query")
        for x, v in zip(faltan, vecs):
            filas = conn.execute(f"SELECT source, content FROM {TABLA_REC300} WHERE tenant_id = %s AND roles && %s::text[] "
                                 "ORDER BY embedding <=> %s::vector LIMIT %s",
                                 (sr.USUARIO["tenant"], sr.USUARIO["roles"], "[" + ",".join(map(str, v)) + "]",
                                  sr.CANDIDATOS)).fetchall()
            cache[f"rec300_base::{x['id']}::{x['lang']}"] = {"ranking": [list(f) for f in filas]}
        guardar()
    rerank(items, cache, guardar, "rec300_base", "rec300")


def rerank(items, cache, guardar, origen, destino):
    def uno(x):
        k = f"{destino}::{x['id']}::{x['lang']}"
        if k in cache:
            return
        cands = [tuple(c) for c in cache[f"{origen}::{x['id']}::{x['lang']}"]["ranking"]]
        orden, tin, tout = a.llamar_haiku(x["question"], cands)
        ordenados = list(dict.fromkeys(orden or [])) + [i for i in range(len(cands)) if i not in (orden or [])]
        cache[k] = {"ranking": [list(cands[i]) for i in ordenados],
                    "costo": (tin * sr.PRECIO["in"] + tout * sr.PRECIO["out"]) / 1e6}
        guardar()
    with ThreadPoolExecutor(8) as ex:
        list(ex.map(uno, items))


# ---------- contextos de generación con el índice rec300 (misma regla que la actividad 4) ----------

def contextos_rec300(items, cache):
    rnd = random.Random(11)
    ctx = {}
    for x in items:
        k = f"{x['id']}::{x['lang']}"
        if x["respondible"]:
            ranking = [tuple(c) for c in cache[f"rec300::{k}"]["ranking"]]
            oro = []
            for i, g in enumerate(x["gold"]):
                c = next((c for c in ranking if i in sr.pasajes_en(c, x["gold"])), None)
                if c is None:  # pasaje partido entre chunks: el mejor chunk de su documento
                    c = next((c for c in ranking if c[0] == Path(g["source"]).stem), ranking[0])
                if c not in oro:
                    oro.append(c)
            distract = [c for c in ranking if not sr.pasajes_en(c, x["gold"]) and c not in oro][:10]
            elegidos = oro + rnd.sample(distract, min(len(distract), rnd.randint(2, 4)))
        else:
            ranking = [tuple(c) for c in cache[f"rec300_base::{k}"]["ranking"]][:10]
            elegidos = rnd.sample(ranking, rnd.randint(3, 5))
        rnd.shuffle(elegidos)
        ctx[k] = {"chunks": [list(c) for c in elegidos]}
    return ctx


# ---------- métricas ----------

def metricas_rec(items, rankings):
    return {(x["id"], x["lang"]): sr.metricas([tuple(c) for c in rankings[f"{x['id']}::{x['lang']}"]], x["gold"])
            for x in items if x["respondible"]}


def metricas_gen(items, ctx, cache):
    out = {}
    for x in items:
        k = f"{x['id']}::{x['lang']}"
        r = {"abstiene": cache[f"clase::{k}"]["valor"] == "abstiene", "respondible": x["respondible"]}
        if x["respondible"]:
            nc, nb = sg.citas(cache[f"gen::{k}"]["respuesta"], ctx[k]["chunks"], x["gold"])
            r.update({m: cache[f"{m}::{k}"]["valor"] for m in ("exactitud", "faithfulness", "answer_relevancy")})
            r["precision_citas"] = nb / nc if nc else None
        out[(x["id"], x["lang"])] = r
    return out


def comparar(base, var, metricas):
    res = {}
    for m in metricas:
        pares = [(base[k][m], var[k][m]) for k in base if k in var and base[k].get(m) is not None and var[k].get(m) is not None]
        dif = [v - b for b, v in pares]
        media, lo, hi = bootstrap(dif)
        res[m] = {"dif": media, "lo": lo, "hi": hi, "n": len(pares), "excluye_0": lo > 0 or hi < 0}
    return res


def main():
    items = sg.items_todos()
    cache = json.loads(CACHE.read_text(encoding="utf-8")) if CACHE.exists() else {}

    def guardar():
        CACHE.write_text(json.dumps(cache, ensure_ascii=False) + "\n", encoding="utf-8")
    rec = json.loads((RES / "suite_recuperacion_cache.json").read_text(encoding="utf-8"))
    resp = [x for x in items if x["respondible"]]

    # --- recuperación ---
    for x in resp:
        cache.setdefault(f"base::{x['id']}::{x['lang']}", rec[f"base::{x['id']}::{x['lang']}"])
    rerank(resp, cache, guardar, "base", "rerank_repeticion")
    if "n_chunks_rec300" not in cache:
        cache["n_chunks_rec300"] = indexar_rec300()
        guardar()
    recuperar_rec300(items, cache, guardar)
    rk = {nombre: {f"{x['id']}::{x['lang']}": cache[f"{pref}::{x['id']}::{x['lang']}"]["ranking"] if pref else
                   rec[f"adoptado::{x['id']}::{x['lang']}"]["ranking"] for x in resp}
          for nombre, pref in (("adoptado", None), ("rerank_repeticion", "rerank_repeticion"), ("sin_rerank", "base"),
                               ("rec300", "rec300"))}
    mrec = {n: metricas_rec(items, r) for n, r in rk.items()}

    # --- generación ---
    ctx_base = json.loads((RES / "contextos_generacion.json").read_text(encoding="utf-8"))
    gen_base = json.loads((RES / "suite_generacion_cache.json").read_text(encoding="utf-8"))
    variantes = {"gen_repeticion": (ctx_base, None), "sin_solo_contexto": (ctx_base, SIS_SIN_SOLO_CONTEXTO),
                 "solo_documentos": (ctx_base, SIS_SOLO_DOCUMENTOS), "rec300": (contextos_rec300(items, cache), None)}
    mgen = {"adoptado": metricas_gen(items, ctx_base, gen_base)}
    costos = {}
    for nombre, (ctx, sistema) in variantes.items():
        ruta = RES / f"sensibilidad_gen_{nombre}.json"
        c = json.loads(ruta.read_text(encoding="utf-8")) if ruta.exists() else {}

        def g(c=c, ruta=ruta):
            ruta.write_text(json.dumps(c, ensure_ascii=False) + "\n", encoding="utf-8")
        sg.generar(items, ctx, c, g, sistema)
        uso = asyncio.run(sg.evaluar(items, ctx, c, g))
        g()
        mgen[nombre] = metricas_gen(items, ctx, c)
        costos[nombre] = (sum(v["costo"] for k, v in c.items() if k.startswith("gen::")),
                          (uso["in"] * sg.PRECIO["in"] + uso["out"] * sg.PRECIO["out"]) / 1e6)
        if nombre == "rec300":
            (RES / "contextos_generacion_rec300.json").write_text(json.dumps(ctx, ensure_ascii=False) + "\n", encoding="utf-8")

    # --- comparación ---
    ruido_rec = comparar(mrec["adoptado"], mrec["rerank_repeticion"], MET_REC)
    ruido_gen = comparar(mgen["adoptado"], mgen["gen_repeticion"], MET_GEN)

    def abst(mg):
        sin = [v for v in mg.values() if not v["respondible"]]
        return sum(v["abstiene"] for v in sin), len(sin), sum(v["abstiene"] for v in mg.values() if v["respondible"])

    def tabla(titulo, comp, ruido):
        print(f"\n### {titulo}\n")
        print("| Métrica | Diferencia | IC 95 % | Ruido (repetición) | Se mueve |")
        print("|---|---|---|---|---|")
        mueve = False
        for m, r in comp.items():
            sale = r["excluye_0"] and abs(r["dif"]) > abs(ruido[m]["dif"])
            mueve |= sale
            print(f"| {m} | {r['dif']:+.3f} | [{r['lo']:+.3f}, {r['hi']:+.3f}] | {ruido[m]['dif']:+.3f} | {'sí' if sale else 'no'} |")
        return mueve

    print("## Huellas de entrada (una suite no ve el componente del otro lado)\n")
    print(f"- Contextos de la suite de generación en sin_rerank, sin_solo_contexto y solo_documentos: {huella(ctx_base)} "
          f"(los mismos de la actividad 4); en rec300: {huella(variantes['rec300'][0])}")
    print(f"- Rankings de la suite de recuperación en sin_solo_contexto y solo_documentos: {huella(rk['adoptado'])} (los de la actividad 2)")

    veredicto = {}
    print("\n## Control de ruido\n")
    tabla("Recuperación: otro reranking sin cambios (rerank_repeticion − adoptado)", ruido_rec, {m: {"dif": 0} for m in MET_REC})
    tabla("Generación: otra generación sin cambios (gen_repeticion − adoptado)", ruido_gen, {m: {"dif": 0} for m in MET_GEN})
    for cambio, en_rec, en_gen in (("sin_rerank", "sin_rerank", None), ("sin_solo_contexto", None, "sin_solo_contexto"),
                                   ("rec300", "rec300", "rec300"), ("solo_documentos", None, "solo_documentos")):
        print(f"\n## Cambio: {cambio}")
        mr = tabla("Suite de recuperación", comparar(mrec["adoptado"], mrec[en_rec], MET_REC), ruido_rec) if en_rec else None
        if mr is None:
            print("\nSuite de recuperación: no se mueve por construcción (no ejecuta el generador; ranking idéntico).")
        mg = tabla("Suite de generación", comparar(mgen["adoptado"], mgen[en_gen], MET_GEN), ruido_gen) if en_gen else None
        if mg is None:
            print("\nSuite de generación: no se mueve por construcción (contextos fijos; ningún componente de recuperación).")
        if en_gen:
            ab, n, falsa = abst(mgen[en_gen])
            ab0, _, falsa0 = abst(mgen["adoptado"])
            print(f"\nAbstención correcta en las sin respuesta: {ab}/{n} (línea base {ab0}/{n}); abstención falsa en respondibles: "
                  f"{falsa} (línea base {falsa0})")
            ab_rep = abst(mgen["gen_repeticion"])[0]
            mg = mg or (abs(ab - ab0) >= 2 and abs(ab - ab0) > abs(ab_rep - ab0))
        veredicto[cambio] = (bool(mr), bool(mg))
    print("\n## Veredicto\n")
    print("| Cambio | Suite de recuperación | Suite de generación |")
    print("|---|---|---|")
    for c, (r, g_) in veredicto.items():
        print(f"| {c} | {'se mueve' if r else 'no se mueve'} | {'se mueve' if g_ else 'no se mueve'} |")
    print(f"\nChunks del índice rec300: {cache['n_chunks_rec300']} (fijo 400/80: 68)")
    costo_rk = sum(v.get("costo", 0) for k, v in cache.items() if k.startswith(("rerank_repeticion::", "rec300::")))
    print(f"Costo: reranking ${costo_rk:.4f}; " + "; ".join(f"{n}: generación ${cg:.4f} + evaluación ${ce:.4f}" for n, (cg, ce) in costos.items()))


if __name__ == "__main__":
    main()
