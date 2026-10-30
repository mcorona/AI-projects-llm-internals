"""Semana 13: corre el loop agéntico sobre tareas del golden set y las verifica.

    python agente/correr.py --corrida piloto --tareas s03 r02 --idiomas es en --esfuerzo low
    python agente/correr.py --corrida eval_haiku_low --k 3 --paralelo 4 --tope-usd 2 --reanudar

- --k: repeticiones por tarea (consistencia, pass^k). Cada repetición es una corrida independiente.
- --paralelo: tareas simultáneas; cada hilo tiene su propia conexión a la base (mismo rol de solo lectura).
- --reanudar: no repite las (tarea, repetición) que ya están en el detalle; permite cortar y seguir.
- --tope-usd: no lanza más tareas cuando el costo acumulado de la corrida lo alcanza.

Escribe las trazas en resultados/trazas/<corrida>.jsonl y el detalle en resultados/<corrida>_detalle.jsonl.
"""
import argparse
import json
import sys
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

AQUI = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(AQUI))
from agente.loop import Agente, Limites, costo  # noqa: E402
from agente.verificar import verificar  # noqa: E402
from herramientas import Contexto, Herramientas  # noqa: E402
from herramientas.conexion import conectar  # noqa: E402
from servidor_mcp.cliente import HerramientasMCP  # noqa: E402


def cargar_tareas(ids, idiomas):
    tareas = []
    for lang in idiomas:
        for linea in open(AQUI / "golden" / f"tareas_{lang}.jsonl", encoding="utf-8"):
            t = json.loads(linea)
            if not ids or t["id"].rsplit("-", 1)[0] in ids:
                tareas.append(t)
    return tareas


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tareas", nargs="*", help="ids base (s03, r02...); sin valor, todas")
    ap.add_argument("--idiomas", nargs="+", default=["es", "en"])
    ap.add_argument("--modelo", default="claude-haiku-5-5")
    ap.add_argument("--esfuerzo", default="low", choices=["low", "medium", "high"])
    ap.add_argument("--corrida", required=True)
    ap.add_argument("--k", type=int, default=1)
    ap.add_argument("--paralelo", type=int, default=1)
    ap.add_argument("--reanudar", action="store_true")
    ap.add_argument("--tope-usd", type=float, default=0.50)
    ap.add_argument("--via", choices=["nativo", "mcp"], default="nativo", help="herramientas nativas o por el servidor MCP")
    a = ap.parse_args()

    tareas = cargar_tareas(a.tareas, a.idiomas)
    res_dir = AQUI / "resultados"
    trazas = res_dir / "trazas" / f"{a.corrida}.jsonl"
    detalle = res_dir / f"{a.corrida}_detalle.jsonl"
    hechas = set()
    if a.reanudar and detalle.exists():
        hechas = {(r["id"], r.get("rep", 0)) for r in map(json.loads, open(detalle, encoding="utf-8"))}
    elif not a.reanudar:
        for p in (trazas, detalle):
            p.unlink(missing_ok=True)
    trabajo = [(t, rep) for rep in range(a.k) for t in tareas if (t["id"], rep) not in hechas]
    lim = Limites()
    print(f"{len(trabajo)} corridas pendientes ({len(tareas)} tareas × k={a.k}; {len(hechas)} ya hechas) · herramientas {a.via} · "
          f"{a.modelo} {a.esfuerzo} · paralelo {a.paralelo} · máximo teórico por corrida ${costo(a.modelo, lim.max_tokens_total, 0):.3f} · "
          f"tope ${a.tope_usd:.2f}")

    conn0, rol = conectar()  # crea el rol una vez; los hilos reusan su DSN
    print(f"base: rol {rol}")
    locales = threading.local()
    candado = threading.Lock()
    total = [sum(r["costo_usd"] for r in map(json.loads, open(detalle, encoding="utf-8"))) if hechas else 0.0]
    conexiones, clientes = [conn0], []

    def herramientas_para(lang):
        if a.via == "mcp":
            d = getattr(locales, "mcp", None) or {}
            if lang not in d:
                d[lang] = HerramientasMCP("analista", lang)
                with candado:
                    clientes.append(d[lang])
            locales.mcp = d
            return d[lang], None
        if not hasattr(locales, "conn"):
            locales.conn = conectar()[0]
            with candado:
                conexiones.append(locales.conn)
        return Herramientas(Contexto.de_usuario("analista", conexion=locales.conn, idioma=lang)), locales.conn

    def una(t, rep):
        with candado:
            if total[0] >= a.tope_usd:
                return None
        h, conn = herramientas_para(t["lang"])
        r = Agente(h, a.modelo, a.esfuerzo, lim, trazas=trazas).resolver({**t, "rep": rep})
        if conn is None:
            conn = getattr(locales, "conn_v", None) or conectar()[0]
            locales.conn_v = conn
        v = verificar(t, r.final, conn, r.estado)
        fila = {"id": t["id"], "rep": rep, "via": a.via, "modelo": a.modelo, "esfuerzo": a.esfuerzo, "tipo": t["tipo"],
                "estado": r.estado, "esperado": t["estado_esperado"], "exito": v["exito"],
                "exactitud_claves": v["exactitud_claves"], "coherencia_claves": v["coherencia_claves"], "claves": v["claves"],
                "pasos": r.pasos, "herramientas": r.herramientas, "pasos_min": t["pasos_min"],
                "errores_herramienta": r.errores_herramienta, "turnos_paralelos": r.turnos_paralelos,
                "tokens_in": r.tokens_in, "tokens_out": r.tokens_out, "costo_usd": round(r.costo_usd, 6),
                "segundos": r.segundos, "motivo": r.motivo, "corrida": r.corrida, "final": r.final}
        with candado:
            total[0] += r.costo_usd
            with open(detalle, "a", encoding="utf-8") as f:
                f.write(json.dumps(fila, ensure_ascii=False, default=str) + "\n")
        print(f"{t['id']:<8}#{rep} {t['tipo']:<13} {r.estado:<19} éxito={'sí' if v['exito'] else 'NO':<3} pasos={r.pasos:<2} "
              f"herr={r.herramientas:<2} err={r.errores_herramienta} ${r.costo_usd:.4f} {r.segundos:>5.1f}s {r.motivo}  "
              f"[acumulado ${total[0]:.3f}]", flush=True)
        return fila

    try:
        with ThreadPoolExecutor(max_workers=a.paralelo) as ex:
            for fut in as_completed([ex.submit(una, t, rep) for t, rep in trabajo]):
                fut.result()
    finally:
        for m in clientes:
            m.cerrar()
        for c in conexiones:
            c.close()
    filas = [json.loads(x) for x in open(detalle, encoding="utf-8")] if detalle.exists() else []
    if total[0] >= a.tope_usd:
        print(f"Tope de ${a.tope_usd:.2f} alcanzado; corre de nuevo con --reanudar para completar.")
    print(f"\nÉxito {sum(f['exito'] for f in filas)}/{len(filas)} · costo ${sum(f['costo_usd'] for f in filas):.4f} · "
          f"detalle: {detalle.relative_to(AQUI)} · trazas: {trazas.relative_to(AQUI)}")


if __name__ == "__main__":
    main()
