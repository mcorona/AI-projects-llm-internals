"""Actividad 3: PDFs con tablas.

1. Genera PDFs (reportlab) desde cuatro documentos con tablas o listas: las fuentes congeladas
   fuentes/tarifas_flete.md y fuentes/matriz_proveedores.md (con preguntas en el golden set) y, del corpus de
   semana 8, ordenes_de_compra.md (tabla de niveles de aprobación) y proveedores.md (tiempos de entrega).
2. Extrae el texto con: pypdf (texto plano), pdfplumber (tablas como filas, resto del texto aparte) y Claude con el
   PDF como entrada (transcripción a Markdown). Referencia superior: el Markdown original, sin pasar por PDF.
3. Métricas, fijadas antes de correr:
   - Celdas presentes: celdas de las tablas originales que aparecen en algún lugar del texto extraído.
   - Celdas en su fila: celdas que aparecen en la misma línea que el resto de su fila (la línea con más coincidencias).
   - Filas íntegras: filas con todas sus celdas en una sola línea.
   Coincidencia de celda: texto exacto (sin negritas, espacios normalizados), con límites de palabra.
   - recall@5: preguntas de PDF del golden set (datasets/integrado_*.jsonl, formato pdf, 5 por idioma). Se indexa
     lo extraído de los 4 PDFs junto con el resto del corpus de semana 8 (sin los 2 documentos que ahora son PDF),
     con chunking fijo 400/80 y bge-m3. Acierto: algún chunk del top 5 viene de ese PDF y contiene la respuesta.
Salidas: tablas en stdout, resultados/pdf_extracciones/ (texto extraído por extractor) y resultados/pdf_tablas_detalle.csv.
Claude se guarda en caché (resultados/pdf_extracciones/claude_<modelo>_<esfuerzo>.json); --regenerar-claude lo rehace.
Requiere reportlab, pypdf, pdfplumber, LM Studio con bge-m3 y, salvo --sin-claude, ANTHROPIC_API_KEY.
"""
import argparse
import base64
import csv
import importlib.util
import json
import math
import os
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from xml.sax.saxutils import escape

AQUI = Path(__file__).resolve().parent
RAIZ = AQUI.parents[0]
REPO = RAIZ.parent
PDF_DIR = RAIZ / "pdf"
RES = RAIZ / "resultados"
EXT_DIR = RES / "pdf_extracciones"
CORPUS = REPO / "semana-08" / "corpus"
sys.path.insert(0, str(REPO / "semana-08" / "experimentos"))
from chunking_pasajes import ESTRATEGIAS  # noqa: E402
from embeddings_comparacion import emb_bge  # noqa: E402

trocear = ESTRATEGIAS["fijo_400_solape_80"]
FUENTES = [RAIZ / "fuentes" / "tarifas_flete.md", RAIZ / "fuentes" / "matriz_proveedores.md",
           CORPUS / "ordenes_de_compra.md", CORPUS / "proveedores.md"]
PRECIOS = json.loads((REPO / "semana-07" / "prices.json").read_text(encoding="utf-8"))
PROMPT = ("Transcribe este documento PDF a Markdown, completo y literal. Conserva cada tabla como tabla Markdown con "
          "todas sus filas y columnas. No resumas, no traduzcas y no agregues texto.")


# ---------- Markdown: bloques y tablas de referencia ----------

def bloques(md):
    out, para, lineas, i = [], [], md.splitlines(), 0

    def vaciar():
        if para:
            out.append(("p", " ".join(para)))
            para.clear()

    while i < len(lineas):
        l = lineas[i].rstrip()
        if not l.strip():
            vaciar()
            i += 1
            continue
        if l.lstrip().startswith("|"):
            vaciar()
            filas = []
            while i < len(lineas) and lineas[i].lstrip().startswith("|"):
                celdas = [c.strip() for c in lineas[i].strip().strip("|").split("|")]
                if not all(re.fullmatch(r":?-{3,}:?", c) for c in celdas):
                    filas.append([c.replace("**", "") for c in celdas])
                i += 1
            out.append(("tabla", filas))
            continue
        if l.startswith("#"):
            vaciar()
            out.append(("h", l.lstrip("#").strip()))
        elif l.startswith("> "):
            vaciar()
            out.append(("nota", l[2:].strip()))
        elif re.match(r"^\s*(- |\d+\. )", l):
            vaciar()
            out.append(("item", l.strip()))
        elif l.startswith("  ") and out and out[-1][0] == "item" and not para:
            out[-1] = ("item", out[-1][1] + " " + l.strip())
        else:
            para.append(l.strip())
        i += 1
    vaciar()
    return out


def tablas_referencia(md):
    return [b[1] for b in bloques(md) if b[0] == "tabla"]


# ---------- Generación de PDFs ----------

def fuente_unicode():
    from reportlab.pdfbase.ttfonts import TTFont
    candidatas = [Path("/System/Library/Fonts/Supplemental/Arial Unicode.ttf"), Path("/Library/Fonts/Arial Unicode.ttf")]
    mpl = importlib.util.find_spec("matplotlib")
    if mpl and mpl.origin:
        candidatas.append(Path(mpl.origin).parent / "mpl-data" / "fonts" / "ttf" / "DejaVuSans.ttf")
    candidatas.append(Path("/System/Library/Fonts/Supplemental/Arial.ttf"))
    for c in candidatas:
        if c.exists():
            f = TTFont("Uni", str(c))
            if all(ord(ch) in f.face.charToGlyph for ch in "→áéíóúñÓ±"):
                return f, c
    raise SystemExit("No se encontró una fuente TTF con '→' y acentos; los PDF tendrían caracteres faltantes.")


def generar_pdf(md_path, pdf_path, estilos):
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import letter
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
    historia = []
    for tipo, cont in bloques(md_path.read_text(encoding="utf-8")):
        if tipo == "tabla":
            datos = [[Paragraph(escape(c), estilos["celda"]) for c in fila] for fila in cont]
            t = Table(datos, repeatRows=1)
            t.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                                   ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#EEEEEE")),
                                   ("VALIGN", (0, 0), (-1, -1), "TOP")]))
            historia += [t, Spacer(1, 8)]
        else:
            texto = escape(cont.replace("**", ""))
            if tipo == "item":
                texto = "• " + re.sub(r"^(- )", "", texto)
            historia.append(Paragraph(texto, estilos[tipo]))
    SimpleDocTemplate(str(pdf_path), pagesize=letter, title=md_path.stem).build(historia)


def generar_pdfs():
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.pdfbase import pdfmetrics
    fuente, ruta = fuente_unicode()
    pdfmetrics.registerFont(fuente)
    estilos = {"h": ParagraphStyle("h", fontName="Uni", fontSize=15, leading=19, spaceAfter=8),
               "nota": ParagraphStyle("nota", fontName="Uni", fontSize=8, leading=10, spaceAfter=8, textColor="#555555"),
               "p": ParagraphStyle("p", fontName="Uni", fontSize=10, leading=13, spaceAfter=6),
               "item": ParagraphStyle("item", fontName="Uni", fontSize=10, leading=13, leftIndent=10, spaceAfter=3),
               "celda": ParagraphStyle("celda", fontName="Uni", fontSize=9, leading=11)}
    PDF_DIR.mkdir(parents=True, exist_ok=True)
    for md in FUENTES:
        generar_pdf(md, PDF_DIR / f"{md.stem}.pdf", estilos)
    print(f"PDFs: {len(FUENTES)} en {PDF_DIR.relative_to(REPO)} (fuente {ruta.name})", file=sys.stderr)


# ---------- Extractores ----------

def ext_original(md, pdf):
    return md.read_text(encoding="utf-8").replace("**", "")


def ext_pypdf(md, pdf):
    from pypdf import PdfReader
    return "\n".join(p.extract_text() or "" for p in PdfReader(str(pdf)).pages)


def ext_pdfplumber(md, pdf):
    import pdfplumber
    partes = []
    with pdfplumber.open(str(pdf)) as doc:
        for pagina in doc.pages:
            tablas = pagina.find_tables()
            cajas = [t.bbox for t in tablas]

            def fuera(o):
                if not all(k in o for k in ("x0", "x1", "top", "bottom")):
                    return True
                cx, cy = (o["x0"] + o["x1"]) / 2, (o["top"] + o["bottom"]) / 2
                return not any(b[0] <= cx <= b[2] and b[1] <= cy <= b[3] for b in cajas)

            partes.append(pagina.filter(fuera).extract_text() or "")
            for t in tablas:
                for fila in t.extract():
                    partes.append(" | ".join((c or "").replace("\n", " ") for c in fila))
    return "\n".join(partes)


def ext_claude(modelo, esfuerzo, regenerar):
    cache_path = EXT_DIR / f"claude_{modelo}_{esfuerzo}.json"
    cache = json.loads(cache_path.read_text(encoding="utf-8")) if cache_path.exists() and not regenerar else {}
    precio = PRECIOS[f"anthropic:{modelo}"]

    def f(md, pdf):
        if pdf.stem not in cache:
            cuerpo = {"model": modelo, "max_tokens": 4000, "output_config": {"effort": esfuerzo},
                      "messages": [{"role": "user", "content": [
                          {"type": "document", "source": {"type": "base64", "media_type": "application/pdf",
                                                          "data": base64.b64encode(pdf.read_bytes()).decode()}},
                          {"type": "text", "text": PROMPT}]}]}
            req = urllib.request.Request("https://api.anthropic.com/v1/messages", data=json.dumps(cuerpo).encode(),
                                         headers={"content-type": "application/json", "anthropic-version": "2023-06-01",
                                                  "x-api-key": os.environ["ANTHROPIC_API_KEY"]})
            t0 = time.perf_counter()
            try:
                with urllib.request.urlopen(req, timeout=180) as r:
                    d = json.loads(r.read())
            except urllib.error.HTTPError as e:
                raise SystemExit(f"API HTTP {e.code} en {pdf.name}: {e.read().decode()[:300]}")
            if d.get("stop_reason") == "max_tokens":
                raise SystemExit(f"Salida truncada por max_tokens en {pdf.name}; no se usa una transcripción incompleta.")
            u = d["usage"]
            cache[pdf.stem] = {"texto": "".join(b.get("text", "") for b in d["content"] if b.get("type") == "text"),
                               "tokens_in": u["input_tokens"], "tokens_out": u["output_tokens"],
                               "latencia_s": round(time.perf_counter() - t0, 2),
                               "costo_usd": round((u["input_tokens"] * precio["in"] + u["output_tokens"] * precio["out"]) / 1e6, 6)}
            EXT_DIR.mkdir(parents=True, exist_ok=True)
            cache_path.write_text(json.dumps(cache, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return cache[pdf.stem]["texto"]
    return f, cache


# ---------- Métricas ----------

def norm_ws(s):
    return re.sub(r"\s+", " ", s.replace("**", "").replace(" ", " ")).strip()


def contiene_celda(texto, celda):
    c = norm_ws(celda)
    return bool(c) and re.search(r"(?<!\w)" + re.escape(c) + r"(?!\w)", norm_ws(texto)) is not None


def metricas_celdas(texto, tablas):
    lineas = [l for l in texto.splitlines() if l.strip()]
    tot = presentes = en_fila = filas_ok = filas = 0
    for tabla in tablas:
        for fila in tabla:
            filas += 1
            tot += len(fila)
            presentes += sum(contiene_celda(texto, c) for c in fila)
            mejor = max((sum(contiene_celda(l, c) for c in fila) for l in lineas), default=0)
            en_fila += mejor
            filas_ok += mejor == len(fila)
    return tot, presentes, en_fila, filas_ok, filas


def coseno(a, b):
    return sum(x * y for x, y in zip(a, b)) / (math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(y * y for y in b)))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--claude-modelo", default="claude-haiku-5-5")
    ap.add_argument("--claude-esfuerzo", default="low", choices=["low", "medium", "high", "xhigh", "max"])
    ap.add_argument("--sin-claude", action="store_true")
    ap.add_argument("--regenerar-claude", action="store_true")
    args = ap.parse_args()

    generar_pdfs()
    extractores = {"original (sin PDF)": ext_original, "pypdf": ext_pypdf, "pdfplumber": ext_pdfplumber}
    cache = {}
    if not args.sin_claude:
        f, cache = ext_claude(args.claude_modelo, args.claude_esfuerzo, args.regenerar_claude)
        extractores[f"Claude {args.claude_modelo} ({args.claude_esfuerzo})"] = f

    EXT_DIR.mkdir(parents=True, exist_ok=True)
    textos = {}
    for nombre, fx in extractores.items():
        textos[nombre] = {md.stem: fx(md, PDF_DIR / f"{md.stem}.pdf") for md in FUENTES}
        clave = re.sub(r"[^a-z0-9]+", "_", nombre.lower()).strip("_")
        for stem, t in textos[nombre].items():
            (EXT_DIR / f"{clave}__{stem}.txt").write_text(t, encoding="utf-8")

    detalle = []
    print("| Extractor | Celdas presentes | Celdas en su fila | Filas íntegras |")
    print("|---|---|---|---|")
    for nombre in extractores:
        agg = [0, 0, 0, 0, 0]
        for md in FUENTES:
            tablas = tablas_referencia(md.read_text(encoding="utf-8"))
            if not tablas:
                continue
            m = metricas_celdas(textos[nombre][md.stem], tablas)
            agg = [a + b for a, b in zip(agg, m)]
            detalle.append({"extractor": nombre, "documento": md.stem, "celdas": m[0], "presentes": m[1],
                            "en_su_fila": m[2], "filas_integras": m[3], "filas": m[4]})
        tot, pres, fila, fok, nf = agg
        print(f"| {nombre} | {pres}/{tot} ({pres / tot:.3f}) | {fila}/{tot} ({fila / tot:.3f}) | {fok}/{nf} |")

    otros = {p.stem: p.read_text(encoding="utf-8") for p in CORPUS.glob("*.md")
             if p.name not in {"ordenes_de_compra.md", "proveedores.md"}}
    preguntas = {lang: [json.loads(l) for l in (RAIZ / "datasets" / f"integrado_{lang}.jsonl").read_text(encoding="utf-8").splitlines()
                        if json.loads(l).get("formato") == "pdf"] for lang in ("es", "en")}
    vq = {lang: emb_bge([q["question"] for q in qs], "query")[0] for lang, qs in preguntas.items()}
    print("\n| Extractor | Idioma | recall@5 |")
    print("|---|---|---|")
    for nombre in extractores:
        docs = {**otros, **textos[nombre]}
        chunks = [(s, c) for s, t in docs.items() for c in trocear(t, s)]
        vc, _ = emb_bge([c for _, c in chunks], "doc")
        for lang, qs in preguntas.items():
            aciertos = 0
            for q, v in zip(qs, vq[lang]):
                top = sorted(range(len(chunks)), key=lambda i: -coseno(v, vc[i]))[:5]
                fuente = Path(q["fuente"]).stem
                ok = any(chunks[i][0] == fuente and norm_ws(q["respuesta"]).lower() in norm_ws(chunks[i][1]).lower() for i in top)
                aciertos += ok
                detalle.append({"extractor": nombre, "documento": fuente, "idioma": lang, "pregunta": q["id"], "acierto_r5": int(ok)})
            print(f"| {nombre} | {lang} | {aciertos}/{len(qs)} ({aciertos / len(qs):.3f}) |")

    if cache:
        c = list(cache.values())
        print(f"\nClaude: {len(c)} PDFs, tokens de entrada {sum(x['tokens_in'] for x in c)}, de salida {sum(x['tokens_out'] for x in c)}, "
              f"costo ${sum(x['costo_usd'] for x in c):.5f}, latencia media {sum(x['latencia_s'] for x in c) / len(c):.1f} s por PDF")
    campos = sorted({k for d in detalle for k in d})
    with (RES / "pdf_tablas_detalle.csv").open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=campos)
        w.writeheader()
        w.writerows(detalle)
    print(f"detalle: {RES / 'pdf_tablas_detalle.csv'}", file=sys.stderr)


if __name__ == "__main__":
    main()
