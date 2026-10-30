"""Verificación de una respuesta del agente contra el golden set (la usan el piloto y la evaluación de la actividad 6).

- estado: el del agente contra estado_esperado.
- exactitud por ejecución, por clave: el SQL que reportó el agente se valida con el guard (como analista) y se vuelve a
  ejecutar completo; sus filas se comparan con las esperadas con el comparador de semana 7 (results_match).
- coherencia, por clave: el valor que el agente reportó coincide con lo que devuelve su propio SQL (detecta respuestas
  que dicen algo distinto de lo que muestran los datos).
- éxito de la tarea: estado correcto y, si se esperaba respuesta, todas las claves exactas.
"""
import importlib.util
from pathlib import Path

from herramientas import Contexto, Herramientas
from herramientas.herramientas import ErrorHerramienta

RAIZ = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location("run_eval7", RAIZ / "semana-07" / "run_eval.py")
re7 = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(re7)


def _filas_de_valor(valor):
    if isinstance(valor, list):
        return [tuple(v) if isinstance(v, (list, tuple)) else (v,) for v in valor]
    return [(valor,)]


def verificar(tarea: dict, final: dict | None, conexion, estado: str) -> dict:
    h = Herramientas(Contexto.de_usuario("analista", conexion=conexion, timeout_ms=15000))
    out = {"estado_ok": estado == tarea["estado_esperado"], "claves": {}}
    reportadas = {x["clave"]: x for x in (final or {}).get("resultados", [])}
    for clave, s in tarea.get("salida", {}).items():
        res = {"reportada": clave in reportadas, "exacta": False, "coherente": False, "error": None}
        if clave in reportadas:
            sql = reportadas[clave]["sql"]
            try:
                h._guard(sql)
                _, filas = h._correr(sql)
                res["exacta"] = re7.results_match([tuple(f) for f in s["esperado"]], filas, s.get("orden", False))
                res["coherente"] = re7.results_match(filas, _filas_de_valor(reportadas[clave]["valor"]), False) or (
                    len(filas) == 1 and len(filas[0]) == 1 and re7.results_match(filas, [(reportadas[clave]["valor"],)]))
            except ErrorHerramienta as e:
                res["error"] = e.tipo
            except Exception as e:  # noqa: BLE001  un SQL que rompe al verificador cuenta como clave no exacta
                res["error"] = f"verificacion: {type(e).__name__}"
        out["claves"][clave] = res
    claves = out["claves"].values()
    out["exito"] = out["estado_ok"] and (tarea["estado_esperado"] != "respondida" or all(c["exacta"] for c in claves))
    out["exactitud_claves"] = sum(c["exacta"] for c in claves) / len(claves) if claves else None
    out["coherencia_claves"] = sum(c["coherente"] for c in claves) / len(claves) if claves else None
    return out
