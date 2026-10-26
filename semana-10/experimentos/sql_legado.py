"""Actividad 2: text-to-SQL sobre un esquema legado.

Set difícil de semana 7 (nlq_hard_validado.jsonl, 43 preguntas por idioma). Cuatro variantes con el mismo modelo:
- copilot:      esquema original (semana-07/schema.sql), control con el mismo modelo.
- legado:       DDL legado con nombres crípticos (legado/esquema_legado.sql), sin diccionario.
- legado_dic:   DDL legado + diccionario de datos completo (legado/diccionario.json).
- legado_rec:   DDL y diccionario solo de las 3 tablas más afines a la pregunta (bge-m3 en LM Studio).
Exactitud por ejecución: el resultado del SQL generado se compara con el del SQL de referencia, con la misma
normalización de semana 7 (semana-07/run_eval.py). El SQL de referencia corre con el search_path por defecto;
en las variantes legado, el SQL generado corre con search_path = legado. Ambos con el rol de solo lectura.

Uso: python3 sql_legado.py --modelo claude-sonnet-5-5 --esfuerzo medium [--variantes copilot,legado,...] [--limite N]
Requiere NLQ_DSN (rol copilot_ro), el esquema legado creado (legado/legado.sql), ANTHROPIC_API_KEY y,
para legado_rec, LM Studio con bge-m3.
"""
import argparse
import csv
import importlib.util
import json
import math
import os
import re
import statistics
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

AQUI = Path(__file__).resolve().parent
RAIZ = AQUI.parents[0]
REPO = RAIZ.parent
LEGADO = RAIZ / "legado"
RES = RAIZ / "resultados"
sys.path.insert(0, str(REPO / "semana-08" / "experimentos"))
_spec = importlib.util.spec_from_file_location("run_eval", REPO / "semana-07" / "run_eval.py")
re7 = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(re7)

PRECIOS = json.loads((REPO / "semana-07" / "prices.json").read_text(encoding="utf-8"))
DICCIONARIO = json.loads((LEGADO / "diccionario.json").read_text(encoding="utf-8"))
ORIGINAL_A_LEGADO = {d["original"]: t for t, d in DICCIONARIO.items()}
DDL_LEGADO = {m.group(1): m.group(0) for m in re.finditer(r"CREATE TABLE (\w+) \(.*?\);",
                                                         (LEGADO / "esquema_legado.sql").read_text(encoding="utf-8"))}
VARIANTES = ("copilot", "legado", "legado_dic", "legado_rec")
K_TABLAS = 3
MAX_TOKENS = 8000


def texto_diccionario(tablas):
    partes = []
    for t in tablas:
        d = DICCIONARIO[t]
        cols = "\n".join(f"  - {c}: {desc}" for c, desc in d["columnas"].items())
        partes.append(f"{t}: {d['descripcion']}\n{cols}")
    return "\n\n".join(partes)


def sistema(esquema, diccionario=None):
    texto = ("You translate questions about an inventory database into one PostgreSQL SELECT statement. "
             "Output only the SQL: no markdown, no comments, no explanation. Use only the tables and columns in "
             "the schema. Never write anything other than a single SELECT or WITH ... SELECT.\n\nSchema:\n" + esquema)
    if diccionario:
        texto += "\n\nData dictionary (meaning of each table and column):\n" + diccionario
    return texto


def coseno(a, b):
    return sum(x * y for x, y in zip(a, b)) / (math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(y * y for y in b)))


def llamar(modelo, esfuerzo, sis, pregunta):
    cuerpo = {"model": modelo, "max_tokens": MAX_TOKENS, "system": sis,
              "messages": [{"role": "user", "content": pregunta}], "output_config": {"effort": esfuerzo}}
    req = urllib.request.Request("https://api.anthropic.com/v1/messages", data=json.dumps(cuerpo).encode("utf-8"),
                                 headers={"Content-Type": "application/json", "anthropic-version": "2023-06-01",
                                          "x-api-key": os.environ["ANTHROPIC_API_KEY"]})
    for intento in range(4):
        t0 = time.perf_counter()
        try:
            with urllib.request.urlopen(req, timeout=180) as r:
                d = json.loads(r.read())
            break
        except urllib.error.HTTPError as e:
            cuerpo_error = e.read().decode("utf-8", "replace")[:500]
            if e.code in (429, 500, 502, 503, 529) and intento < 3:
                time.sleep(2 ** (intento + 1))
                continue
            # Error no reintentable (o reintentos agotados): se registra y la corrida sigue.
            print(f"  API HTTP {e.code}: {cuerpo_error}", file=sys.stderr)
            return f"API HTTP {e.code}: {cuerpo_error}", 0, 0, round(time.perf_counter() - t0, 3), "error_api"
    texto = "".join(b.get("text", "") for b in d["content"] if b.get("type") == "text")
    return (texto, d["usage"]["input_tokens"], d["usage"]["output_tokens"], round(time.perf_counter() - t0, 3),
            d.get("stop_reason"))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--modelo", required=True)
    ap.add_argument("--esfuerzo", required=True, choices=["low", "medium", "high", "xhigh", "max"])
    ap.add_argument("--variantes", default=",".join(VARIANTES))
    ap.add_argument("--limite", type=int, default=0, help="solo las primeras N preguntas por idioma (prueba)")
    ap.add_argument("--reanudar", action="store_true", help="salta las combinaciones pregunta-variante ya guardadas en el CSV")
    args = ap.parse_args()
    variantes = args.variantes.split(",")
    precio = PRECIOS[f"anthropic:{args.modelo}"]

    items = [json.loads(l) for l in (REPO / "semana-07" / "datasets" / "nlq_hard_validado.jsonl").read_text(encoding="utf-8").splitlines()]
    if args.limite:
        items = [x for lang in ("es", "en") for x in [i for i in items if i["lang"] == lang][:args.limite]]

    conn_ref = re7.conectar(os.environ["NLQ_DSN"])
    conn_leg = re7.conectar(os.environ["NLQ_DSN"])
    conn_leg.execute("SET search_path = legado")
    vistas = {r[0] for r in conn_leg.execute(
        "SELECT table_name FROM information_schema.views WHERE table_schema = 'legado'").fetchall()}
    if vistas != set(DICCIONARIO):
        raise SystemExit(f"El esquema legado no está completo para el rol de lectura: {sorted(vistas)}. Corre legado/legado.sql.")
    gold = {x["id"]: re7.ejecutar(conn_ref, x["sql"]) for x in items}

    rec_vecs, entradas = {}, []
    if "legado_rec" in variantes:
        from embeddings_comparacion import emb_bge
        entradas = list(DICCIONARIO)
        ev, _ = emb_bge([texto_diccionario([t]) for t in entradas], "doc")
        qv, _ = emb_bge([x["question"] for x in items], "query")
        rec_vecs = {x["id"]: v for x, v in zip(items, qv)}
        ent_vecs = dict(zip(entradas, ev))

    esquema_copilot = (REPO / "semana-07" / "schema.sql").read_text(encoding="utf-8")
    ddl_completo = "\n".join(DDL_LEGADO[t] for t in DICCIONARIO)
    RES.mkdir(parents=True, exist_ok=True)
    salida = RES / f"sql_legado_detalle_{args.modelo}_{args.esfuerzo}{'_prueba' if args.limite else ''}.csv"
    CAMPOS = ["id", "lang", "variante", "categoria", "ok", "tablas_necesarias", "tablas_recuperadas",
              "recuperacion_completa", "tokens_in", "tokens_out", "latencia_s", "costo_usd", "sql"]
    detalle = []
    if args.reanudar and salida.exists():
        for f in csv.DictReader(salida.open(encoding="utf-8")):
            for k in ("ok", "tokens_in", "tokens_out"):
                f[k] = int(f[k])
            f["latencia_s"], f["costo_usd"] = float(f["latencia_s"]), float(f["costo_usd"])
            f["recuperacion_completa"] = "" if f["recuperacion_completa"] == "" else int(f["recuperacion_completa"])
            if f["categoria"] != "error_api":  # los errores de API se vuelven a intentar
                detalle.append(f)
        print(f"reanudando: {len(detalle)} combinaciones ya hechas (los errores de API se reintentan)", file=sys.stderr)
    hechas = {(d["id"], d["variante"]) for d in detalle}
    # El archivo se reescribe con lo ya hecho y se completa con lo nuevo, sin duplicados.
    fh = salida.open("w", encoding="utf-8", newline="")
    escritor = csv.DictWriter(fh, fieldnames=CAMPOS)
    escritor.writeheader()
    escritor.writerows(detalle)
    fh.flush()
    for x in items:
        tablas_ref = re7.tablas_del_sql(x["sql"])
        necesarias = {ORIGINAL_A_LEGADO[t] for t in tablas_ref if t in ORIGINAL_A_LEGADO}
        for var in variantes:
            if (x["id"], var) in hechas:
                continue
            recuperadas = None
            if var == "copilot":
                sis, conn = sistema(esquema_copilot), conn_ref
            elif var == "legado":
                sis, conn = sistema(ddl_completo), conn_leg
            elif var == "legado_dic":
                sis, conn = sistema(ddl_completo, texto_diccionario(list(DICCIONARIO))), conn_leg
            else:
                orden = sorted(entradas, key=lambda t: -coseno(rec_vecs[x["id"]], ent_vecs[t]))
                recuperadas = orden[:K_TABLAS]
                sis = sistema("\n".join(DDL_LEGADO[t] for t in recuperadas), texto_diccionario(recuperadas))
                conn = conn_leg
            texto, tin, tout, lat, stop = llamar(args.modelo, args.esfuerzo, sis, x["question"])
            sql = re7.extraer_sql(texto)
            if stop == "error_api":
                cat, sql = "error_api", None
            elif stop == "max_tokens":
                cat = "salida_truncada"
            elif sql is None:
                cat = "no_es_select"
            else:
                try:
                    cat = "correcta" if re7.results_match(gold[x["id"]], re7.ejecutar(conn, sql), x["order_matters"]) else "resultado_distinto"
                except Exception as e:  # noqa: BLE001  (cualquier error de SQL cuenta como fallo de ejecución)
                    cat = "error_sql"
            detalle.append({"id": x["id"], "lang": x["lang"], "variante": var, "categoria": cat, "ok": int(cat == "correcta"),
                            "tablas_necesarias": "|".join(sorted(necesarias)),
                            "tablas_recuperadas": "|".join(recuperadas) if recuperadas else "",
                            "recuperacion_completa": "" if recuperadas is None else int(necesarias <= set(recuperadas)),
                            "tokens_in": tin, "tokens_out": tout, "latencia_s": lat,
                            "costo_usd": round((tin * precio["in"] + tout * precio["out"]) / 1e6, 7), "sql": sql or texto[:300]})
            escritor.writerow(detalle[-1])
            fh.flush()
        print(f"{x['id']}: " + " ".join(f"{d['variante']}={d['categoria']}" for d in detalle if d["id"] == x["id"]), file=sys.stderr)
    fh.close()

    print(f"\nModelo {args.modelo}, esfuerzo {args.esfuerzo}. Precio: {precio['in']} / {precio['out']} USD por millón.\n")
    print("| Variante | Idioma | Exactitud | Correctas | Errores SQL | Resultado distinto | Recuperación completa de tablas | Costo por pregunta (USD) | Latencia p50 (s) | Tokens de salida (media) |")
    print("|---|---|---|---|---|---|---|---|---|---|")
    for var in variantes:
        for lang in ("es", "en"):
            f = [d for d in detalle if d["variante"] == var and d["lang"] == lang]
            ok = sum(d["ok"] for d in f)
            rec = f"{sum(d['recuperacion_completa'] for d in f)}/{len(f)}" if var == "legado_rec" else "-"
            print(f"| {var} | {lang} | {ok / len(f):.3f} | {ok}/{len(f)} | {sum(d['categoria'] == 'error_sql' for d in f)} | "
                  f"{sum(d['categoria'] == 'resultado_distinto' for d in f)} | {rec} | "
                  f"{statistics.mean(d['costo_usd'] for d in f):.5f} | {statistics.median(d['latencia_s'] for d in f):.1f} | "
                  f"{statistics.mean(d['tokens_out'] for d in f):.0f} |")
    otros = [d for d in detalle if d["categoria"] in ("salida_truncada", "no_es_select")]
    api = [d for d in detalle if d["categoria"] == "error_api"]
    print(f"\nSalidas truncadas o que no son SELECT: {len(otros)}. Errores de API: {len(api)}. "
          f"Costo total: ${sum(d['costo_usd'] for d in detalle):.4f}")
    print(f"detalle: {salida}", file=sys.stderr)


if __name__ == "__main__":
    main()
