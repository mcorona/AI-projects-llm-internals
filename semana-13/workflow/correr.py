"""Semana 13, actividad 6: corre el workflow de semana 10 sobre el golden set (k repeticiones) y lo verifica.

    python workflow/correr.py --k 3 --paralelo 4 --tope-usd 0.50 --reanudar
"""
import argparse
import json
import sys
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

AQUI = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(AQUI))
from agente.correr import cargar_tareas  # noqa: E402
from agente.verificar import verificar  # noqa: E402
from herramientas import Contexto, Herramientas  # noqa: E402
from herramientas.conexion import conectar  # noqa: E402
from workflow.semana10 import resolver  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tareas", nargs="*")
    ap.add_argument("--idiomas", nargs="+", default=["es", "en"])
    ap.add_argument("--corrida", default="workflow_s10")
    ap.add_argument("--k", type=int, default=3)
    ap.add_argument("--paralelo", type=int, default=4)
    ap.add_argument("--reanudar", action="store_true")
    ap.add_argument("--tope-usd", type=float, default=0.50)
    a = ap.parse_args()
    detalle = AQUI / "resultados" / f"{a.corrida}_detalle.jsonl"
    hechas = set()
    if a.reanudar and detalle.exists():
        hechas = {(r["id"], r["rep"]) for r in map(json.loads, open(detalle, encoding="utf-8"))}
    else:
        detalle.unlink(missing_ok=True)
    tareas = cargar_tareas(a.tareas, a.idiomas)
    trabajo = [(t, rep) for rep in range(a.k) for t in tareas if (t["id"], rep) not in hechas]
    total = [sum(r["costo_usd"] for r in map(json.loads, open(detalle, encoding="utf-8"))) if hechas else 0.0]
    print(f"{len(trabajo)} corridas pendientes · workflow semana 10 (Haiku 5.5 low) · paralelo {a.paralelo} · "
          f"tope ${a.tope_usd:.2f} sobre el acumulado de la corrida (ya ${total[0]:.3f})")
    conectar()
    locales, candado, conexiones = threading.local(), threading.Lock(), []

    def una(t, rep):
        with candado:
            if total[0] >= a.tope_usd:
                return
        if not hasattr(locales, "conn"):
            locales.conn = conectar()[0]
            with candado:
                conexiones.append(locales.conn)
        h = Herramientas(Contexto.de_usuario("analista", conexion=locales.conn, idioma=t["lang"]))
        r = resolver(t, h)
        v = verificar(t, r["final"], locales.conn, r["estado"])
        fila = {"id": t["id"], "rep": rep, "modelo": "workflow semana 10", "esfuerzo": "low", "tipo": t["tipo"],
                "estado": r["estado"], "esperado": t["estado_esperado"], "ruta": r["ruta"], "exito": v["exito"],
                "exactitud_claves": v["exactitud_claves"], "claves": v["claves"], "pasos": r["pasos"],
                "herramientas": r["herramientas"], "errores_herramienta": r["errores_herramienta"],
                "tokens_in": r["tokens_in"], "tokens_out": r["tokens_out"], "costo_usd": round(r["costo_usd"], 6),
                "segundos": r["segundos"], "final": r["final"]}
        with candado:
            total[0] += r["costo_usd"]
            with open(detalle, "a", encoding="utf-8") as f:
                f.write(json.dumps(fila, ensure_ascii=False, default=str) + "\n")
        print(f"{t['id']:<8}#{rep} {t['tipo']:<13} ruta={r['ruta']:<10} {r['estado']:<11} éxito={'sí' if v['exito'] else 'NO':<3} "
              f"${r['costo_usd']:.4f} {r['segundos']:>5.1f}s [acumulado ${total[0]:.3f}]", flush=True)

    try:
        with ThreadPoolExecutor(max_workers=a.paralelo) as ex:
            for fut in as_completed([ex.submit(una, t, rep) for t, rep in trabajo]):
                fut.result()
    finally:
        for c in conexiones:
            c.close()
    filas = [json.loads(x) for x in open(detalle, encoding="utf-8")]
    print(f"\nÉxito {sum(f['exito'] for f in filas)}/{len(filas)} · costo ${sum(f['costo_usd'] for f in filas):.4f} · {detalle.name}")


if __name__ == "__main__":
    main()
