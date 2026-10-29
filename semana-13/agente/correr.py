"""Semana 13: corre el loop agéntico sobre tareas del golden set y las verifica.

    python agente/correr.py --tareas s03 r02 c02 v01 a01 n01 --idiomas es en --esfuerzo low --corrida piloto

Escribe las trazas en resultados/trazas/<corrida>.jsonl y el detalle en resultados/<corrida>_detalle.jsonl.
Antes de llamar a la API imprime el costo máximo posible según los límites, y se detiene si supera --tope-usd.
"""
import argparse
import json
import sys
from pathlib import Path

AQUI = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(AQUI))
from agente.loop import Agente, Limites, costo  # noqa: E402
from agente.verificar import verificar  # noqa: E402
from herramientas import Contexto, Herramientas  # noqa: E402
from herramientas.conexion import conectar  # noqa: E402
from servidor_mcp.cliente import HerramientasMCP  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tareas", nargs="*", help="ids base (s03, r02...); sin valor, todas")
    ap.add_argument("--idiomas", nargs="+", default=["es", "en"])
    ap.add_argument("--modelo", default="claude-haiku-5-5")
    ap.add_argument("--esfuerzo", default="low", choices=["low", "medium", "high"])
    ap.add_argument("--corrida", required=True)
    ap.add_argument("--tope-usd", type=float, default=0.50)
    ap.add_argument("--via", choices=["nativo", "mcp"], default="nativo", help="herramientas nativas o por el servidor MCP")
    a = ap.parse_args()

    tareas = []
    for lang in a.idiomas:
        for linea in open(AQUI / "golden" / f"tareas_{lang}.jsonl", encoding="utf-8"):
            t = json.loads(linea)
            if not a.tareas or t["id"].rsplit("-", 1)[0] in a.tareas:
                tareas.append(t)
    lim = Limites()
    maximo = len(tareas) * costo(a.modelo, lim.max_tokens_total, 0)
    print(f"{len(tareas)} tareas · herramientas {a.via} · {a.modelo} {a.esfuerzo} · costo máximo teórico ${maximo:.2f} si todas agotan los límites; tope de la corrida ${a.tope_usd:.2f}")

    conn, rol = conectar()
    print(f"base: rol {rol}")
    res_dir = AQUI / "resultados"
    trazas = res_dir / "trazas" / f"{a.corrida}.jsonl"
    detalle = res_dir / f"{a.corrida}_detalle.jsonl"
    for p in (trazas, detalle):
        p.unlink(missing_ok=True)
    total, clientes = 0.0, {}
    for t in tareas:
        if total >= a.tope_usd:
            print(f"Tope de ${a.tope_usd:.2f} alcanzado; se detiene.")
            break
        if a.via == "mcp":
            if t["lang"] not in clientes:
                clientes[t["lang"]] = HerramientasMCP("analista", t["lang"])
            h = clientes[t["lang"]]
        else:
            h = Herramientas(Contexto.de_usuario("analista", conexion=conn, idioma=t["lang"]))
        r = Agente(h, a.modelo, a.esfuerzo, lim, trazas=trazas).resolver(t)
        v = verificar(t, r.final, conn, r.estado)
        total += r.costo_usd
        fila = {"id": t["id"], "via": a.via, "tipo": t["tipo"], "estado": r.estado, "esperado": t["estado_esperado"], "exito": v["exito"],
                "exactitud_claves": v["exactitud_claves"], "coherencia_claves": v["coherencia_claves"], "claves": v["claves"],
                "pasos": r.pasos, "herramientas": r.herramientas, "pasos_min": t["pasos_min"], "errores_herramienta": r.errores_herramienta,
                "turnos_paralelos": r.turnos_paralelos, "tokens_in": r.tokens_in, "tokens_out": r.tokens_out,
                "costo_usd": round(r.costo_usd, 6), "segundos": r.segundos, "motivo": r.motivo, "corrida": r.corrida,
                "final": r.final}
        with open(detalle, "a", encoding="utf-8") as f:
            f.write(json.dumps(fila, ensure_ascii=False, default=str) + "\n")
        print(f"{t['id']:<8} {t['tipo']:<13} {r.estado:<19} éxito={'sí' if v['exito'] else 'NO':<3} "
              f"pasos={r.pasos:<2} herr={r.herramientas:<2} err={r.errores_herramienta} par={r.turnos_paralelos} "
              f"${r.costo_usd:.4f} {r.segundos:>5.1f}s {r.motivo}")
    for m in clientes.values():
        m.cerrar()
    filas = [json.loads(x) for x in open(detalle, encoding="utf-8")]
    n = len(filas)
    print(f"\nÉxito {sum(f['exito'] for f in filas)}/{n} · costo ${sum(f['costo_usd'] for f in filas):.4f} · "
          f"trazas: {trazas.relative_to(AQUI)} ({sum(1 for _ in open(trazas))} eventos)")


if __name__ == "__main__":
    main()
