"""Actividad 4: contextual retrieval con claude-haiku-5-5.

Para cada chunk de semana 8 (fijo 400/80, 57 chunks), Haiku recibe el documento completo y el chunk,
y escribe un contexto breve. El embedding (bge-m3) se calcula sobre "contexto + chunk" y se indexa en
OpenSearch como `semana9_ctx`. El campo `content` guarda el chunk original, así que la comparación
contra el pasaje de referencia es la misma que en la línea base (`semana8`).

- Los contextos se guardan en resultados/contextos.jsonl y se reutilizan (pasa --regenerar para
  volver a generarlos). El costo de indexado se calcula con los tokens guardados.
- Si algún contexto sale vacío, el script se detiene y no indexa.
- Evalúa base y seguimiento (pregunta original); los casos de permiso van en la actividad 5.

Salidas: tabla en stdout, resultados/contextual_detalle.csv (una fila por consulta).
Requiere LM Studio con bge-m3, OpenSearch con el índice semana8 y ANTHROPIC_API_KEY.
"""
import csv
import hashlib
import json
import os
import statistics
import sys
import time
from pathlib import Path

AQUI = Path(__file__).resolve().parent
RAIZ = AQUI.parents[0]
DATOS = RAIZ / "datasets"
RES = RAIZ / "resultados"
sys.path.insert(0, str(RAIZ.parent / "semana-08" / "experimentos"))
from cargar_vector_dbs import DIM, filas, http as http_os  # noqa: E402
from chunking_pasajes import CORPUS  # noqa: E402
from embeddings_comparacion import emb_bge  # noqa: E402
from reranking import MODELO, PRECIO, http as http_api, metricas  # noqa: E402

OPENSEARCH = os.getenv("OPENSEARCH_URL", "http://localhost:9200")
BASE = "semana8"
CTX = "semana9_ctx"
CACHE = RES / "contextos.jsonl"
SISTEMA = ("Sitúas fragmentos de documentos para mejorar su búsqueda. Recibes un documento completo y uno de "
           "sus fragmentos. Escribe un contexto breve (una o dos oraciones, en el idioma del documento) que diga "
           "de qué documento y de qué tema trata el fragmento. Responde SOLO con el contexto, sin repetir el "
           "fragmento ni añadir texto adicional.")


def huella(f):
    return hashlib.sha1(f"{f['source']}|{f['chunk_index']}|{f['content']}".encode("utf-8")).hexdigest()[:12]


# max_tokens alto: Haiku usa tokens de razonamiento (bloque thinking) antes del texto (ver HyDE, actividad 3).
def contexto(documento, fragmento):
    contenido = f"<documento>\n{documento}\n</documento>\n\n<fragmento>\n{fragmento}\n</fragmento>"
    r = http_api("POST", "https://api.anthropic.com/v1/messages", {
        "model": MODELO, "max_tokens": 1500, "system": SISTEMA,
        "messages": [{"role": "user", "content": contenido}]},
        {"x-api-key": os.environ["ANTHROPIC_API_KEY"], "anthropic-version": "2023-06-01"})
    texto = "".join(b.get("text", "") for b in r["content"] if b.get("type") == "text").strip()
    tipos = "|".join(b.get("type", "?") for b in r["content"])
    return texto, r["usage"]["input_tokens"], r["usage"]["output_tokens"], tipos


def generar_contextos(fs, regenerar):
    cache = {}
    if CACHE.exists() and not regenerar:
        for linea in CACHE.read_text(encoding="utf-8").splitlines():
            fila = json.loads(linea)
            cache[fila["huella"]] = fila
    docs = {p.name: p.read_text(encoding="utf-8") for p in CORPUS.glob("*.md")}
    nuevos = 0
    for f in fs:
        h = huella(f)
        if h in cache:
            continue
        t0 = time.perf_counter()
        texto, tin, tout, tipos = contexto(docs[f["source"]], f["content"])
        cache[h] = {"huella": h, "source": f["source"], "chunk_index": f["chunk_index"], "contexto": texto,
                    "tokens_in": tin, "tokens_out": tout, "tipos_bloque": tipos,
                    "latencia_ms": round((time.perf_counter() - t0) * 1000)}
        nuevos += 1
    RES.mkdir(parents=True, exist_ok=True)
    with CACHE.open("w", encoding="utf-8") as out:
        for f in fs:
            out.write(json.dumps(cache[huella(f)], ensure_ascii=False) + "\n")
    print(f"contextos: {len(fs)} ({nuevos} generados ahora, {len(fs) - nuevos} reutilizados)", file=sys.stderr)
    return [cache[huella(f)] for f in fs]


def cargar_ctx(fs, ctxs, vecs):
    http_os("DELETE", f"{OPENSEARCH}/{CTX}", ignorar=(404,))
    http_os("PUT", f"{OPENSEARCH}/{CTX}", {
        "settings": {"index": {"knn": True}},
        "mappings": {"properties": {
            "source": {"type": "keyword"},
            "chunk_index": {"type": "integer"},
            "content": {"type": "text"},
            "contexto": {"type": "text"},
            "embedding": {"type": "knn_vector", "dimension": DIM,
                          "method": {"name": "hnsw", "space_type": "cosinesimil", "engine": "lucene"}},
        }}})
    lineas = []
    for f, c, v in zip(fs, ctxs, vecs):
        lineas.append(json.dumps({"index": {"_index": CTX, "_id": str(f["id"])}}))
        lineas.append(json.dumps({"source": f["source"], "chunk_index": f["chunk_index"],
                                  "content": f["content"], "contexto": c["contexto"], "embedding": v}))
    http_os("POST", f"{OPENSEARCH}/_bulk", "\n".join(lineas) + "\n", ctype="application/x-ndjson")
    http_os("POST", f"{OPENSEARCH}/{CTX}/_refresh")
    return http_os("GET", f"{OPENSEARCH}/{CTX}/_count")["count"]


def tamano(indice):
    return http_os("GET", f"{OPENSEARCH}/{indice}/_stats/store")["_all"]["primaries"]["store"]["size_in_bytes"]


def buscar(indice, vec, k):
    r = http_api("POST", f"{OPENSEARCH}/{indice}/_search",
                 {"size": k, "query": {"knn": {"embedding": {"vector": vec, "k": k}}}})
    return [(h["_source"]["source"], h["_source"]["content"]) for h in r["hits"]["hits"]]


def promedio(filas_m):
    n = len(filas_m)
    return [sum(f[i] for f in filas_m) / n for i in range(3)]


def main():
    print(f"precio usado (prices.json, Haiku): {PRECIO}", file=sys.stderr)
    fs = filas()
    n_base = http_os("GET", f"{OPENSEARCH}/{BASE}/_count")["count"]
    if n_base != len(fs):
        raise SystemExit(f"El índice {BASE} tiene {n_base} documentos y el chunking da {len(fs)}; no son comparables.")

    ctxs = generar_contextos(fs, "--regenerar" in sys.argv)
    vacios = [c for c in ctxs if not c["contexto"]]
    if vacios:
        raise SystemExit(f"{len(vacios)} contextos vacíos (p. ej. {vacios[0]['source']} #{vacios[0]['chunk_index']}); no se indexa.")
    for c in ctxs[:3]:
        print(f"<!-- contexto {c['source']} #{c['chunk_index']}: {c['contexto']} -->", file=sys.stderr)

    vecs, _ = emb_bge([c["contexto"] + "\n\n" + f["content"] for f, c in zip(fs, ctxs)], "doc")
    n_ctx = cargar_ctx(fs, ctxs, vecs)

    tin = sum(c["tokens_in"] for c in ctxs)
    tout = sum(c["tokens_out"] for c in ctxs)
    costo = (tin * PRECIO["in"] + tout * PRECIO["out"]) / 1e6
    lat = [c["latencia_ms"] for c in ctxs]
    print(f"\nIndexado: {n_ctx} chunks en {CTX}; tokens entrada {tin}, salida {tout}; "
          f"costo único ${costo:.5f}; latencia por contexto p50 {statistics.median(lat):.0f} ms; "
          f"tamaño {BASE} {tamano(BASE)} B, {CTX} {tamano(CTX)} B\n")

    detalle = []
    print("| Tipo | Idioma | Índice | recall@5 | nDCG@10 | MRR |")
    print("|---|---|---|---|---|---|")
    for idioma in ("es", "en"):
        items = [json.loads(l) for l in (DATOS / f"avanzado_{idioma}.jsonl").read_text(encoding="utf-8").splitlines()]
        for tipo in ("base", "seguimiento"):
            sel = [x for x in items if x["tipo"] == tipo]
            vq, _ = emb_bge([x["question"] for x in sel], "query")
            filas_b = [metricas(x, buscar(BASE, v, 10)) for x, v in zip(sel, vq)]
            filas_c = [metricas(x, buscar(CTX, v, 10)) for x, v in zip(sel, vq)]
            for x, fb, fc in zip(sel, filas_b, filas_c):
                detalle.append({"id": x["id"], "tipo": tipo, "idioma": idioma, "pregunta": x["question"],
                                "acierto_base_r5": int(fb[0] > 0), "acierto_contextual_r5": int(fc[0] > 0)})
            for nombre, fm in ((BASE, filas_b), (CTX, filas_c)):
                r5, nd, mr = promedio(fm)
                print(f"| {tipo} | {idioma} | {nombre} | {r5:.3f} | {nd:.3f} | {mr:.3f} |")

    salida = RES / "contextual_detalle.csv"
    with salida.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(detalle[0].keys()))
        w.writeheader()
        w.writerows(detalle)
    print(f"detalle por consulta: {salida}", file=sys.stderr)


if __name__ == "__main__":
    main()
