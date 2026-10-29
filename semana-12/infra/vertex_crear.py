"""Semana 12, actividad 5: data stores y apps de Vertex AI Search (Agent Search), con la cuenta de servicio semana12-operador
por impersonación. Requiere gcp_crear.sh y gcp_bucket_crear.sh (dueño del proyecto) y el paquete de la actividad 2.

Dos data stores no estructurados en `global`, con los mismos metadatos que Bedrock (tenant_id, roles, source, doc_id,
tipo) declarados filtrables en el esquema antes de importar:
- vx-adm (modo administrado): los originales, parseados y troceados por el servicio con el layout parser y el chunking
  predeterminado (500 tokens). Vertex no acepta Markdown ni imágenes sueltas como documentos: el layout parser lee HTML,
  PDF, DOCX, PPTX y XLSX (no TXT) y no importa JPG ni PNG. Como lo haría un cliente, los .md se convierten a HTML y los JPG
  y PNG a un PDF de una página (el layout parser hace OCR), sin cambiar su contenido.
- vx-ctl (modo controlado): los 101 chunks del pipeline propio, un documento .txt por chunk, sin re-trocear (parser digital,
  sin chunking): aísla la calidad del índice y del ranking.
Cada data store tiene su app de búsqueda (edición Enterprise, sin add-on de LLM). Ids en estado_gcp.json (fuera de Git).
Idempotente: reutiliza lo que ya existe por id.
"""
import html
import io
import json
import re
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

AQUI = Path(__file__).resolve().parent
PAQUETE = AQUI.parent / "ingesta" / "paquete"
CFG = (AQUI / "config.sh").read_text()
PREFIJO = re.search(r"^PREFIJO=(\S+)", CFG, re.M).group(1)
PROYECTO = re.search(r"^GCP_PROYECTO=\$\{GCP_PROYECTO:-([^}]+)\}", CFG, re.M).group(1)
UBICACION = "global"
BUCKET = f"{PREFIJO}-docs-{PROYECTO}"
SA = f"{PREFIJO}-operador@{PROYECTO}.iam.gserviceaccount.com"
API = f"https://discoveryengine.googleapis.com/v1/projects/{PROYECTO}/locations/{UBICACION}/collections/default_collection"
ESTADO = AQUI / "estado_gcp.json"
ESQUEMA = {"$schema": "https://json-schema.org/draft/2020-12/schema", "type": "object", "properties": {
    "tenant_id": {"type": "string", "indexable": True, "retrievable": True},
    "roles": {"type": "array", "items": {"type": "string", "indexable": True, "retrievable": True}},
    "source": {"type": "string", "indexable": True, "retrievable": True},
    "doc_id": {"type": "string", "retrievable": True},
    "tipo": {"type": "string", "indexable": True, "retrievable": True},
    "chunk": {"type": "number", "retrievable": True}}}
STORES = {
    "vx-adm": {"jsonl": "vertex_vx-adm.jsonl", "procesamiento": {
        "chunkingConfig": {"layoutBasedChunkingConfig": {"chunkSize": 500, "includeAncestorHeadings": False}},
        "defaultParsingConfig": {"layoutParsingConfig": {}}}},
    "vx-ctl": {"jsonl": "vertex_controlado_chunks.jsonl", "procesamiento": {"defaultParsingConfig": {"digitalParsingConfig": {}}}},
}


def token():
    r = subprocess.run(["gcloud", "auth", "print-access-token", f"--impersonate-service-account={SA}"],
                       capture_output=True, text=True)
    if r.returncode:
        raise SystemExit(f"No se pudo impersonar {SA}: {r.stderr.strip()[-300:]}")
    return r.stdout.strip()


def api(metodo, url, cuerpo=None, ok404=False):
    req = urllib.request.Request(url, method=metodo, data=None if cuerpo is None else json.dumps(cuerpo).encode(),
                                 headers={"Authorization": f"Bearer {token()}", "Content-Type": "application/json",
                                          "x-goog-user-project": PROYECTO})
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            t = r.read()
            return json.loads(t) if t else {}
    except urllib.error.HTTPError as e:
        if ok404 and e.code == 404:
            return None
        raise SystemExit(f"{metodo} {url.split('/v1/')[-1]}: HTTP {e.code} {e.read().decode()[:600]}")


def esperar(op, que):
    t0 = time.time()
    while not op.get("done"):
        time.sleep(15)
        op = api("GET", f"https://discoveryengine.googleapis.com/v1/{op['name']}")
        print(f"  {que}: {int(time.time() - t0)} s", flush=True)
    if "error" in op:
        raise SystemExit(f"{que}: {op['error']}")
    return op, int(time.time() - t0)


# ---------- conversión de formatos para el modo administrado ----------

def md_a_html(md, titulo):
    """Markdown del corpus (títulos, listas, tablas, negritas) a HTML simple, sin cambiar el texto."""
    linea = lambda s: re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", html.escape(s))  # noqa: E731
    out, i, ls = [f"<!doctype html><html><head><meta charset='utf-8'><title>{html.escape(titulo)}</title></head><body>"], 0, md.splitlines()
    while i < len(ls):
        s = ls[i].rstrip()
        if s.startswith("|"):
            filas = []
            while i < len(ls) and ls[i].strip().startswith("|"):
                celdas = [c.strip() for c in ls[i].strip().strip("|").split("|")]
                if not all(re.fullmatch(r":?-{2,}:?", c) for c in celdas):
                    filas.append(celdas)
                i += 1
            out.append("<table>" + "".join("<tr>" + "".join(f"<{'th' if j == 0 else 'td'}>{linea(c)}</{'th' if j == 0 else 'td'}>"
                                                              for c in f) + "</tr>" for j, f in enumerate(filas)) + "</table>")
            continue
        m = re.match(r"(#{1,6})\s+(.*)", s)
        if m:
            out.append(f"<h{len(m.group(1))}>{linea(m.group(2))}</h{len(m.group(1))}>")
        elif re.match(r"\s*([-*]|\d+\.)\s+", s):
            items = []
            while i < len(ls) and re.match(r"\s*([-*]|\d+\.)\s+", ls[i]):
                items.append(re.sub(r"^\s*([-*]|\d+\.)\s+", "", ls[i]))
                i += 1
            out.append("<ul>" + "".join(f"<li>{linea(x)}</li>" for x in items) + "</ul>")
            continue
        elif s.startswith(">"):
            out.append(f"<blockquote>{linea(s.lstrip('> '))}</blockquote>")
        elif s:
            out.append(f"<p>{linea(s)}</p>")
        i += 1
    return "\n".join(out + ["</body></html>"])


def preparar_administrado(tmp):
    """Convierte y lista los documentos de vx-adm: (ruta local, objeto GCS, entrada JSONL)."""
    from PIL import Image
    filas = []
    for l in (PAQUETE / "vertex_administrado.jsonl").read_text(encoding="utf-8").splitlines():
        d = json.loads(l)
        rel = d["content"]["uri"].split(f"gs://{BUCKET}/", 1)[1]
        orig = PAQUETE / rel
        if orig.suffix == ".md":
            dest, mime = tmp / "vx-adm" / Path(rel).with_suffix(".html"), "text/html"
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(md_a_html(orig.read_text(encoding="utf-8"), d["structData"]["source"]), encoding="utf-8")
        elif orig.suffix in (".jpg", ".png"):
            dest, mime = tmp / "vx-adm" / Path(rel).with_suffix(".pdf"), "application/pdf"
            dest.parent.mkdir(parents=True, exist_ok=True)
            Image.open(orig).convert("RGB").save(dest, "PDF", resolution=150)
        else:
            dest, mime = tmp / "vx-adm" / rel, d["content"]["mimeType"]
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(orig.read_bytes())
        obj = f"vx-adm/{dest.relative_to(tmp / 'vx-adm')}"
        filas.append({**d, "content": {"mimeType": mime, "uri": f"gs://{BUCKET}/{obj}"}})
    (tmp / "vertex_vx-adm.jsonl").write_text("".join(json.dumps(f, ensure_ascii=False) + "\n" for f in filas), encoding="utf-8")
    return filas


def subir(tmp):
    imp = [f"--impersonate-service-account={SA}"]
    subprocess.run(["gcloud", "storage", "rsync", "--recursive", "--delete-unmatched-destination-objects", str(PAQUETE / "controlado"),
                    f"gs://{BUCKET}/controlado", *imp, "--quiet"], check=True)
    subprocess.run(["gcloud", "storage", "rsync", "--recursive", "--delete-unmatched-destination-objects", str(tmp / "vx-adm"),
                    f"gs://{BUCKET}/vx-adm", *imp, "--quiet"], check=True)
    subprocess.run(["gcloud", "storage", "cp", str(PAQUETE / "vertex_controlado_chunks.jsonl"), str(tmp / "vertex_vx-adm.jsonl"),
                    f"gs://{BUCKET}/", *imp, "--quiet"], check=True)


def main():
    stores = sys.argv[1:] or list(STORES)
    estado = json.loads(ESTADO.read_text()) if ESTADO.exists() else {}
    with tempfile.TemporaryDirectory() as t:
        tmp = Path(t)
        n = preparar_administrado(tmp)
        print(f"vx-adm: {len(n)} documentos ({sum(f['content']['mimeType'] == 'text/html' for f in n)} md→HTML, "
              f"{sum(Path(f['content']['uri']).suffix == '.pdf' for f in n)} PDF, 4 de ellos imágenes convertidas)")
        subir(tmp)
        print(f"subido a gs://{BUCKET}/ (controlado/, vx-adm/ y los JSONL)")
    for sid in stores:
        ds_id, cfg = f"{PREFIJO}-{sid}", STORES[sid]
        ds = api("GET", f"{API}/dataStores/{ds_id}", ok404=True)
        if ds is None:
            op = api("POST", f"{API}/dataStores?dataStoreId={ds_id}", {
                "displayName": ds_id, "industryVertical": "GENERIC", "solutionTypes": ["SOLUTION_TYPE_SEARCH"],
                "contentConfig": "CONTENT_REQUIRED", "documentProcessingConfig": cfg["procesamiento"]})
            esperar(op, f"crear data store {ds_id}")
            print(f"data store {ds_id}: creado")
        op = api("PATCH", f"{API}/dataStores/{ds_id}/schemas/default_schema", {"jsonSchema": json.dumps(ESQUEMA)})
        if op and not op.get("done", True):
            esperar(op, f"esquema {ds_id}")
        print(f"data store {ds_id}: esquema con tenant_id y roles filtrables")
        op = api("POST", f"{API}/dataStores/{ds_id}/branches/0/documents:import", {
            "gcsSource": {"inputUris": [f"gs://{BUCKET}/{cfg['jsonl']}"], "dataSchema": "document"},
            "reconciliationMode": "FULL"})
        op, seg = esperar(op, f"importar {ds_id}")
        meta = op.get("metadata", {})
        errores = op.get("response", {}).get("errorSamples", [])
        print(f"importación {ds_id}: {meta.get('successCount', 0)} éxitos, {meta.get('failureCount', 0)} fallos, {seg} s")
        for e in errores[:8]:
            print("   fallo:", str(e.get("message", e))[:300])
        eng_id = f"{ds_id}-app"
        if api("GET", f"{API}/engines/{eng_id}", ok404=True) is None:
            op = api("POST", f"{API}/engines?engineId={eng_id}", {
                "displayName": eng_id, "solutionType": "SOLUTION_TYPE_SEARCH", "industryVertical": "GENERIC",
                "dataStoreIds": [ds_id], "searchEngineConfig": {"searchTier": "SEARCH_TIER_ENTERPRISE", "searchAddOns": []}})
            esperar(op, f"crear app {eng_id}")
            print(f"app {eng_id}: creada (Enterprise, sin add-on de LLM)")
        estado[sid] = {"data_store": ds_id, "engine": eng_id, "importados": int(meta.get("successCount", 0)),
                       "fallidos": int(meta.get("failureCount", 0)), "importacion_s": seg}
        ESTADO.write_text(json.dumps(estado, indent=1))
    print(json.dumps(estado, indent=1))


if __name__ == "__main__":
    main()
