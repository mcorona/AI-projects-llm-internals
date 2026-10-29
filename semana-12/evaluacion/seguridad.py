"""Semana 12, actividad 6: fuga por rol y entre tenants en los RAG administrados, con las pruebas de semana 10.

Casos (los mismos de semana 10, actividad 8):
- rol: cada pregunta documental o no textual del golden integrado de semana 10 (15 + 15 por idioma) cuyo documento de
  referencia no está abierto a todos los roles; usuario del tenant alfa con un solo rol SIN acceso a ese documento (el
  primero, en el orden de semana 10, que no está entre sus roles);
- tenant: las 10 preguntas multitenant de semana 9 por idioma (sus documentos existen en alfa y en beta con cifras
  distintas), con un usuario de alfa y otro de beta, ambos con todos los roles.
Sistemas: las 4 Knowledge Bases de Bedrock (Retrieve), RetrieveAndGenerate sobre adm-fijo-bda (la opción administrada
adoptada; se revisan las referencias citadas) y los 2 data stores de Vertex AI Search (búsqueda híbrida), con el filtro
de tenant y roles dentro de la consulta y top 20.
Fuga = un chunk en los resultados cuyo tenant o roles reales no autorizan al usuario. El tenant y el documento se toman
de la ubicación del archivo (no de los metadatos que devuelve el servicio) y los roles del documento, del manifiesto del
paquete de ingesta (actividad 2). Se cuentan también los casos en que aparece el documento de referencia prohibido.
Control: las mismas consultas SIN filtro en una KB y un data store; deben aparecer chunks no autorizados, lo que muestra
que la prueba detecta la fuga cuando no hay filtro. Además se registra cuántos resultados devuelve cada consulta filtrada:
si el filtro se aplicara después del top k, los usuarios con un solo rol recibirían menos de 20.
Salida: resultados/seguridad.md (escrito a mano con estos datos), seguridad_resumen.json y seguridad_detalle.csv.
Costo: Retrieve y búsqueda de Vertex (centavos); RetrieveAndGenerate con Haiku 4.5 (≈ $0.17).
"""
import csv
import json
import statistics
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import suites as s  # noqa: E402  (helpers de Bedrock y Vertex, golden y asistente)

a, RAIZ, REPO = s.a, s.RAIZ, s.REPO
ORDEN_ROLES = ["ventas", "calidad", "compras", "almacen", "finanzas", "operaciones"]  # semana 10, seguridad.py
TODOS = sorted({r for rs in a.ROLES.values() for r in rs})
MANIF = json.loads((RAIZ / "ingesta" / "paquete" / "manifiesto.json").read_text(encoding="utf-8"))
ROLES_DOC = {(d["tenant_id"], d["source"]): set(d["roles"]) for d in MANIF["documentos"]}
RES = RAIZ / "resultados"


def casos():
    out = []
    for lang in ("es", "en"):
        for l in (REPO / "semana-10" / "datasets" / f"integrado_{lang}.jsonl").read_text(encoding="utf-8").splitlines():
            x = json.loads(l)
            if x["tipo"] not in ("documental", "no_textual"):
                continue
            fuente = Path(x["gold"][0]["source"] if x.get("gold") else x["fuente"]).stem
            libre = [r for r in ORDEN_ROLES if r not in a.ROLES[fuente]]
            if libre:
                out.append({"tipo": "rol", "id": x["id"], "lang": lang, "question": x["question"], "fuente": fuente,
                            "usuario": {"tenant": "alfa", "roles": [libre[0]]}})
        for l in (REPO / "semana-09" / "datasets" / f"multitenant_{lang}.jsonl").read_text(encoding="utf-8").splitlines():
            x = json.loads(l)
            for t in ("alfa", "beta"):
                out.append({"tipo": "tenant", "id": x["id"], "lang": lang, "question": x["question"],
                            "fuente": Path(x["source"]).stem, "usuario": {"tenant": t, "roles": TODOS}})
    return out


def autorizado(tenant, source, u):
    return tenant == u["tenant"] and bool(ROLES_DOC.get((tenant, source), set()) & set(u["roles"]))


def filtro_bedrock(u):
    roles = [{"listContains": {"key": "roles", "value": r}} for r in u["roles"]]
    return {"andAll": [{"equals": {"key": "tenant_id", "value": u["tenant"]}}, roles[0] if len(roles) == 1 else {"orAll": roles}]}


def filtro_vertex(u):
    return f'tenant_id: ANY("{u["tenant"]}") AND roles: ANY(' + ",".join(f'"{r}"' for r in u["roles"]) + ")"


def ubicacion_s3(uri):
    """s3://<bucket>/administrado/<tenant>/<archivo> o .../controlado/chunks/<tenant>/<doc>__NNN.txt"""
    partes = uri.split("/")
    stem = Path(partes[-1]).stem.removesuffix("_p1")
    return partes[-2], stem.split("__")[0]


def bedrock(config, c, con_filtro=True, cli=None):
    vsc = {"numberOfResults": 20}
    if con_filtro:
        vsc["filter"] = filtro_bedrock(c["usuario"])
    r = cli.retrieve(knowledgeBaseId=s._kb(config), retrievalQuery={"text": c["question"]},
                     retrievalConfiguration={"vectorSearchConfiguration": vsc})
    return [ubicacion_s3(z.get("location", {}).get("s3Location", {}).get("uri", "")) for z in r["retrievalResults"]]


def bedrock_rag(config, c, cli, modelo):
    r = cli.retrieve_and_generate(input={"text": c["question"]}, retrieveAndGenerateConfiguration={
        "type": "KNOWLEDGE_BASE", "knowledgeBaseConfiguration": {"knowledgeBaseId": s._kb(config), "modelArn": modelo,
            "retrievalConfiguration": {"vectorSearchConfiguration": {"numberOfResults": 5, "filter": filtro_bedrock(c["usuario"])}}}})
    return [ubicacion_s3(ref.get("location", {}).get("s3Location", {}).get("uri", ""))
            for cit in r.get("citations", []) for ref in cit.get("retrievedReferences", [])]


def vertex(store, c, con_filtro=True):
    proy, _ = s._vx_conf()
    estado = json.loads((RAIZ / "infra" / "estado_gcp.json").read_text(encoding="utf-8"))[store]
    url = (f"https://discoveryengine.googleapis.com/v1/projects/{proy}/locations/global/collections/default_collection/"
           f"engines/{estado['engine']}/servingConfigs/default_search:search")
    cuerpo = {"query": c["question"], "pageSize": 20, "relevanceThreshold": "LOWEST", "queryExpansionSpec": {"condition": "AUTO"},
              "contentSearchSpec": {"searchResultMode": "CHUNKS" if store == "vx-adm" else "DOCUMENTS"}}
    if con_filtro:
        cuerpo["filter"] = filtro_vertex(c["usuario"])
    out = []
    for z in s._vx(url, cuerpo).get("results", []):
        if "chunk" in z:
            partes = z["chunk"].get("documentMetadata", {}).get("uri", "").split("/")
            out.append((partes[-2], Path(partes[-1]).stem.removesuffix("_p1")))
        else:
            t, stem, _ = z["document"]["id"].split("__")
            out.append((t, stem))
    return out


def medir(nombre, fn, cs, hilos=1):
    def uno(c):
        t0 = time.perf_counter()
        res = fn(c)
        no_aut = [(t, src) for t, src in res if not autorizado(t, src, c["usuario"])]
        return {"sistema": nombre, "tipo": c["tipo"], "id": c["id"], "lang": c["lang"], "usuario": json.dumps(c["usuario"]),
                "resultados": len(res), "no_autorizados": len(no_aut),
                "documento_prohibido": int(c["tipo"] == "rol" and any(src == c["fuente"] for _, src in res)
                                           or c["tipo"] == "tenant" and any(t != c["usuario"]["tenant"] for t, _ in res)),
                "ejemplo": "; ".join(f"{t}/{src}" for t, src in no_aut[:3]), "lat": round(time.perf_counter() - t0, 3)}
    with ThreadPoolExecutor(hilos) as ex:
        filas = list(ex.map(uno, cs))
    print(f"{nombre}: {sum(f['no_autorizados'] for f in filas)} chunks no autorizados en {len(filas)} consultas", flush=True)
    return filas


def main():
    cs = casos()
    print(f"casos: {sum(c['tipo'] == 'rol' for c in cs)} por rol, {sum(c['tipo'] == 'tenant' for c in cs)} entre tenants")
    cli = s._aws("bedrock-agent-runtime")
    cuenta = s._aws("sts").get_caller_identity()["Account"]
    modelo = f"arn:aws:bedrock:us-east-1:{cuenta}:inference-profile/{s.PERFIL_RAG}"
    filas = []
    for cfg in ("adm-pred", "adm-fijo", "adm-fijo-bda", "ctl-chunks"):
        filas += medir(f"bedrock {cfg}", lambda c, cfg=cfg: bedrock(cfg, c, True, cli), cs)
    filas += medir("bedrock adm-fijo-bda RetrieveAndGenerate", lambda c: bedrock_rag("adm-fijo-bda", c, cli, modelo), cs, hilos=4)
    for st in ("vx-adm", "vx-ctl"):
        filas += medir(f"vertex {st}", lambda c, st=st: vertex(st, c, True), cs)
    control = medir("CONTROL bedrock ctl-chunks sin filtro", lambda c: bedrock("ctl-chunks", c, False, cli), cs)
    control += medir("CONTROL vertex vx-ctl sin filtro", lambda c: vertex("vx-ctl", c, False), cs)

    resumen = {"casos": {"rol": sum(c["tipo"] == "rol" for c in cs), "tenant": sum(c["tipo"] == "tenant" for c in cs)},
               "sistemas": {}, "control_sin_filtro": {}}
    for destino, fs in (("sistemas", filas), ("control_sin_filtro", control)):
        for nombre in dict.fromkeys(f["sistema"] for f in fs):
            g = [f for f in fs if f["sistema"] == nombre]
            resumen[destino][nombre] = {
                tipo: {"consultas": len(h), "chunks_no_autorizados": sum(f["no_autorizados"] for f in h),
                       "consultas_con_fuga": sum(1 for f in h if f["no_autorizados"]),
                       "documento_prohibido": sum(f["documento_prohibido"] for f in h),
                       "resultados_media": round(statistics.mean(f["resultados"] for f in h), 1),
                       "resultados_min": min(f["resultados"] for f in h)}
                for tipo in ("rol", "tenant") for h in [[f for f in g if f["tipo"] == tipo]]}
    resumen["fuga_total"] = sum(v[t]["chunks_no_autorizados"] for v in resumen["sistemas"].values() for t in ("rol", "tenant"))
    (RES / "seguridad_resumen.json").write_text(json.dumps(resumen, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    with (RES / "seguridad_detalle.csv").open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(filas[0].keys()))
        w.writeheader()
        w.writerows(filas + control)
    print("\n| Sistema | Tipo | Consultas | Chunks no autorizados | Consultas con fuga | Doc. prohibido | Resultados (media / mín) |")
    print("|---|---|---|---|---|---|---|")
    for destino in ("sistemas", "control_sin_filtro"):
        for nombre, v in resumen[destino].items():
            for t in ("rol", "tenant"):
                x = v[t]
                print(f"| {nombre} | {t} | {x['consultas']} | {x['chunks_no_autorizados']} | {x['consultas_con_fuga']} | "
                      f"{x['documento_prohibido']} | {x['resultados_media']} / {x['resultados_min']} |")
    print(f"\nFUGA TOTAL CON FILTRO: {resumen['fuga_total']} (debe ser 0)")
    if resumen["fuga_total"]:
        raise SystemExit("HAY FUGA")


if __name__ == "__main__":
    main()
