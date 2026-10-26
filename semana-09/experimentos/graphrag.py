"""Actividad 7: GraphRAG (comparación acotada) con claude-haiku-5-5.

1. Haiku extrae entidades y relaciones de cada uno de los 57 chunks de semana 8 (fijo 400/80).
   Caché: resultados/grafo_extraccion.jsonl (--regenerar para rehacerla). Si algún chunk no devuelve
   JSON válido, el script se detiene sin cargar nada.
2. El grafo se guarda en Postgres: semana9.entidades (chunk_id, entidad, tipo) y
   semana9.relaciones (chunk_id, origen, relacion, destino). Nombres normalizados (minúsculas, sin acentos).
3. Compara, solo en preguntas multi-salto (dos documentos por pregunta), en dos sets reportados por separado:
   - compuestas (datasets/multisalto_*.jsonl): la pregunta nombra ambos temas (control);
   - puente (datasets/multisalto_puente_*.jsonl): la entidad que une los documentos no aparece en la
     pregunta (caso más favorable para GraphRAG).
   Métodos:
   - V:   vectorial (OpenSearch semana8, bge-m3), top 10.
   - V+R: vectorial top 20 + reranking con Haiku, top 10.
   - G:   3 semillas vectoriales + chunks conectados por entidades compartidas o por una relación,
          con peso 1/df; las entidades en más del 30 % de los chunks no conectan.
   - G+Q: Haiku extrae entidades de la pregunta; los chunks que las mencionan (peso 1/df) se fusionan
          con el vectorial por RRF (k=60).
Métricas fijadas antes de correr: recall@5 (sobre los dos pasajes), ambos pasajes en el top 5,
nDCG@10 y MRR; costo por consulta y latencia p50. Costo único de extracción por separado.

Requiere PG_ADMIN_DSN, LM Studio con bge-m3, OpenSearch con el índice semana8 y ANTHROPIC_API_KEY.
"""
import csv
import hashlib
import json
import os
import re
import statistics
import sys
import time
import unicodedata
from collections import defaultdict
from pathlib import Path

import psycopg

AQUI = Path(__file__).resolve().parent
RAIZ = AQUI.parents[0]
RES = RAIZ / "resultados"
DATOS = RAIZ / "datasets"
sys.path.insert(0, str(RAIZ.parent / "semana-08" / "experimentos"))
from cargar_vector_dbs import filas  # noqa: E402
from embeddings_comparacion import emb_bge  # noqa: E402
from reranking import MODELO, PRECIO, buscar_vectorial, http as http_api, llamar_haiku, metricas  # noqa: E402

CACHE = RES / "grafo_extraccion.jsonl"
UMBRAL_COMUN = 0.30
SEMILLAS = 3
K = 10
SIS_EXT = ("Extraes un grafo de conocimiento de fragmentos de documentos internos de una empresa de inventarios. "
           "Entidades: roles, áreas, documentos, procesos, tipos de producto o SKU, CEDIS o sitios, proveedores, "
           "métricas, plazos y montos. Usa nombres canónicos cortos en español, en singular y minúsculas "
           "(p. ej., 'gerente de compras', 'sku crítico', 'cedis monterrey'). Relaciones: verbos cortos entre dos "
           "entidades del fragmento (p. ej., 'aprueba', 'tiene plazo', 'aplica a'). "
           "Responde SOLO JSON: {\"entidades\": [{\"nombre\": \"...\", \"tipo\": \"...\"}], "
           "\"relaciones\": [{\"origen\": \"...\", \"relacion\": \"...\", \"destino\": \"...\"}]}")
SIS_Q = ("Extraes las entidades de una pregunta para buscarlas en un grafo de conocimiento de una empresa de "
         "inventarios. Devuelve los nombres en español, en singular y minúsculas, como aparecerían en un documento "
         "interno, aunque la pregunta esté en inglés. Responde SOLO JSON: {\"entidades\": [\"...\"]}")


def normalizar(s):
    s = unicodedata.normalize("NFKD", str(s).lower())
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = re.sub(r"[^a-z0-9%$.,/ ]+", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return re.sub(r"^(el|la|los|las|un|una) ", "", s)


# max_tokens alto: Haiku razona (bloque thinking) antes del JSON. Con 2000, 14 de 57 extracciones se
# cortaron en el límite y los JSON válidos llegaron a 1969 tokens de salida.
def llamar(sistema, contenido, max_tokens=6000):
    r = http_api("POST", "https://api.anthropic.com/v1/messages", {
        "model": MODELO, "max_tokens": max_tokens, "system": sistema,
        "messages": [{"role": "user", "content": contenido}]},
        {"x-api-key": os.environ["ANTHROPIC_API_KEY"], "anthropic-version": "2023-06-01"})
    texto = "".join(b.get("text", "") for b in r["content"] if b.get("type") == "text")
    return texto, r["usage"]["input_tokens"], r["usage"]["output_tokens"]


def json_de(texto):
    m = re.search(r"\{.*\}", texto, re.S)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except json.JSONDecodeError:
        return None


def costo(tin, tout):
    return (tin * PRECIO["in"] + tout * PRECIO["out"]) / 1e6


def huella(f):
    return hashlib.sha1(f"{f['source']}|{f['chunk_index']}|{f['content']}".encode("utf-8")).hexdigest()[:12]


def extraer(fs, regenerar):
    cache = {}
    if CACHE.exists() and not regenerar:
        for linea in CACHE.read_text(encoding="utf-8").splitlines():
            fila = json.loads(linea)
            cache[fila["huella"]] = fila
    nuevos = 0
    for f in fs:
        h = huella(f)
        if h in cache and cache[h]["ok"]:
            continue
        t0 = time.perf_counter()
        texto, tin, tout = llamar(SIS_EXT, f"Documento: {f['source']}\n\nFragmento:\n{f['content']}")
        d = json_de(texto)
        ok = isinstance(d, dict) and isinstance(d.get("entidades"), list) and isinstance(d.get("relaciones"), list)
        cache[h] = {"huella": h, "id": f["id"], "source": f["source"], "chunk_index": f["chunk_index"], "ok": ok,
                    "entidades": d.get("entidades", []) if ok else [], "relaciones": d.get("relaciones", []) if ok else [],
                    "tokens_in": tin, "tokens_out": tout, "latencia_ms": round((time.perf_counter() - t0) * 1000)}
        nuevos += 1
    RES.mkdir(parents=True, exist_ok=True)
    with CACHE.open("w", encoding="utf-8") as out:
        for f in fs:
            out.write(json.dumps(cache[huella(f)], ensure_ascii=False) + "\n")
    print(f"extracción: {len(fs)} chunks ({nuevos} extraídos ahora, {len(fs) - nuevos} reutilizados)", file=sys.stderr)
    return [cache[huella(f)] for f in fs]


def cargar_grafo(conn, ext):
    conn.execute("CREATE SCHEMA IF NOT EXISTS semana9")
    conn.execute("DROP TABLE IF EXISTS semana9.relaciones")
    conn.execute("DROP TABLE IF EXISTS semana9.entidades")
    conn.execute("CREATE TABLE semana9.entidades (chunk_id int NOT NULL, entidad text NOT NULL, tipo text, "
                 "PRIMARY KEY (chunk_id, entidad))")
    conn.execute("CREATE TABLE semana9.relaciones (chunk_id int NOT NULL, origen text NOT NULL, relacion text NOT NULL, "
                 "destino text NOT NULL)")
    with conn.cursor() as cur:
        for e in ext:
            vistos = {}
            for ent in e["entidades"]:
                n = normalizar(ent.get("nombre", "")) if isinstance(ent, dict) else ""
                if n:
                    vistos.setdefault(n, ent.get("tipo"))
            for rel in e["relaciones"]:
                if not isinstance(rel, dict):
                    continue
                o, d = normalizar(rel.get("origen", "")), normalizar(rel.get("destino", ""))
                if o and d:
                    vistos.setdefault(o, None)
                    vistos.setdefault(d, None)
                    cur.execute("INSERT INTO semana9.relaciones VALUES (%s,%s,%s,%s)",
                                (e["id"], o, normalizar(rel.get("relacion", "")) or "relacionado", d))
            for n, tipo in vistos.items():
                cur.execute("INSERT INTO semana9.entidades VALUES (%s,%s,%s)", (e["id"], n, tipo))


def leer_grafo(conn, n_chunks):
    menciones = defaultdict(set)
    for cid, ent in conn.execute("SELECT chunk_id, entidad FROM semana9.entidades"):
        menciones[ent].add(cid)
    vecinos_rel = defaultdict(set)
    for o, d in conn.execute("SELECT DISTINCT origen, destino FROM semana9.relaciones"):
        vecinos_rel[o].add(d)
        vecinos_rel[d].add(o)
    df = {e: len(c) for e, c in menciones.items()}
    comunes = {e for e, n in df.items() if n > UMBRAL_COMUN * n_chunks}
    ents_chunk = defaultdict(set)
    for e, cs in menciones.items():
        for c in cs:
            ents_chunk[c].add(e)
    n_rel = conn.execute("SELECT count(*) FROM semana9.relaciones").fetchone()[0]
    return menciones, vecinos_rel, df, comunes, ents_chunk, n_rel


def expandir(semillas, menciones, vecinos_rel, df, comunes, ents_chunk):
    peso = defaultdict(float)
    for s in semillas:
        for e in ents_chunk[s] - comunes:
            for c in menciones[e]:
                peso[c] += 1 / df[e]
            for e2 in vecinos_rel[e] - comunes:
                for c in menciones.get(e2, ()):
                    peso[c] += 0.5 / df[e2]
    return [c for c, _ in sorted(peso.items(), key=lambda x: -x[1]) if c not in semillas]


def coincidencias(nombres, menciones, comunes):
    encontradas = set()
    for q in nombres:
        for e in menciones:
            if e in comunes:
                continue
            if q == e or (len(q) >= 4 and (q in e or e in q)):
                encontradas.add(e)
    return encontradas


def rrf(*rankings, k=60):
    puntos = defaultdict(float)
    for r in rankings:
        for i, c in enumerate(r):
            puntos[c] += 1 / (k + i + 1)
    return [c for c, _ in sorted(puntos.items(), key=lambda x: -x[1])]


def main():
    fs = filas()
    por_id = {f["id"]: (f["source"], f["content"]) for f in fs}
    a_id = {(f["source"], f["content"]): f["id"] for f in fs}
    ext = extraer(fs, "--regenerar" in sys.argv)
    malos = [e for e in ext if not e["ok"]]
    if malos:
        raise SystemExit(f"{len(malos)} chunks sin JSON válido (p. ej. {malos[0]['source']} #{malos[0]['chunk_index']}); no se carga el grafo.")

    conn = psycopg.connect(os.environ["PG_ADMIN_DSN"], autocommit=True)
    cargar_grafo(conn, ext)
    menciones, vecinos_rel, df, comunes, ents_chunk, n_rel = leer_grafo(conn, len(fs))
    tin_x, tout_x = sum(e["tokens_in"] for e in ext), sum(e["tokens_out"] for e in ext)
    print(f"Grafo: {len(menciones)} entidades únicas, {n_rel} relaciones; {len(comunes)} entidades genéricas excluidas "
          f"de la expansión ({', '.join(sorted(comunes)[:8])}). Extracción: {tin_x} tokens de entrada, {tout_x} de salida, "
          f"costo único ${costo(tin_x, tout_x):.5f}; p50 {statistics.median(e['latencia_ms'] for e in ext):.0f} ms por chunk.\n")

    detalle = []
    print("| Set | Idioma | Método | recall@5 | Ambos pasajes en top 5 | nDCG@10 | MRR | Costo por consulta (USD) | Latencia p50 (ms) | Fallos |")
    print("|---|---|---|---|---|---|---|---|---|---|")
    for conjunto, prefijo, idioma in [(c, p_, i) for c, p_ in (("compuestas", "multisalto"), ("puente", "multisalto_puente"))
                                      for i in ("es", "en")]:
        items = [json.loads(l) for l in (DATOS / f"{prefijo}_{idioma}.jsonl").read_text(encoding="utf-8").splitlines()]
        vq, _ = emb_bge([x["question"] for x in items], "query")
        res = {m: {"filas": [], "lat": [], "tin": 0, "tout": 0, "fallos": 0} for m in ("V", "V+R", "G", "G+Q")}
        for x, v in zip(items, vq):
            t0 = time.perf_counter()
            cands = buscar_vectorial(v, 20)
            t_vec = (time.perf_counter() - t0) * 1000
            ids_vec = [a_id[c] for c in cands]
            rankings = {"V": ids_vec[:K]}
            res["V"]["lat"].append(t_vec)

            t0 = time.perf_counter()
            orden, a, b = llamar_haiku(x["question"], cands)
            res["V+R"]["lat"].append(t_vec + (time.perf_counter() - t0) * 1000)
            res["V+R"]["tin"] += a
            res["V+R"]["tout"] += b
            if orden is None:
                res["V+R"]["fallos"] += 1
                rankings["V+R"] = ids_vec[:K]
            else:
                ordenados = list(dict.fromkeys(orden))
                rankings["V+R"] = [ids_vec[i] for i in (ordenados + [i for i in range(len(cands)) if i not in ordenados])[:K]]

            t0 = time.perf_counter()
            sem = ids_vec[:SEMILLAS]
            exp = expandir(sem, menciones, vecinos_rel, df, comunes, ents_chunk)
            g = list(dict.fromkeys(sem + exp + ids_vec))[:K]
            res["G"]["lat"].append(t_vec + (time.perf_counter() - t0) * 1000)
            rankings["G"] = g

            t0 = time.perf_counter()
            texto, a, b = llamar(SIS_Q, f"Pregunta: {x['question']}", max_tokens=1500)
            res["G+Q"]["tin"] += a
            res["G+Q"]["tout"] += b
            d = json_de(texto)
            nombres = [normalizar(n) for n in d.get("entidades", []) if isinstance(n, str)] if isinstance(d, dict) else []
            if not nombres:
                res["G+Q"]["fallos"] += 1
            encontradas = coincidencias(nombres, menciones, comunes)
            score = defaultdict(float)
            for e in encontradas:
                for c in menciones[e]:
                    score[c] += 1 / df[e]
            por_ent = [c for c, _ in sorted(score.items(), key=lambda z: -z[1])]
            rankings["G+Q"] = rrf(ids_vec, por_ent)[:K]
            res["G+Q"]["lat"].append(t_vec + (time.perf_counter() - t0) * 1000)

            fila_det = {"set": conjunto, "id": x["id"], "idioma": idioma, "pregunta": x["question"], "entidades_pregunta": "|".join(nombres),
                        "entidades_en_grafo": "|".join(sorted(encontradas))}
            for m, r in rankings.items():
                met = metricas(x, [por_id[c] for c in r])
                res[m]["filas"].append(met)
                fila_det[f"recall5_{m}"] = round(met[0], 3)
            detalle.append(fila_det)

        n = len(items)
        for m in ("V", "V+R", "G", "G+Q"):
            fm = res[m]["filas"]
            r5 = sum(f[0] for f in fm) / n
            ambos = sum(1 for f in fm if f[0] >= 1.0)
            nd = sum(f[1] for f in fm) / n
            mr = sum(f[2] for f in fm) / n
            c = costo(res[m]["tin"], res[m]["tout"]) / n
            print(f"| {conjunto} | {idioma} | {m} | {r5:.3f} | {ambos}/{n} | {nd:.3f} | {mr:.3f} | {c:.6f} | "
                  f"{statistics.median(res[m]['lat']):.0f} | {res[m]['fallos']} |")
    conn.close()

    salida = RES / "graphrag_detalle.csv"
    with salida.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(detalle[0].keys()))
        w.writeheader()
        w.writerows(detalle)
    print(f"detalle por consulta: {salida}", file=sys.stderr)


if __name__ == "__main__":
    main()
