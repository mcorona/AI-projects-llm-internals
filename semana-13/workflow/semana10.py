"""Semana 13, actividad 6: el asistente de semana 10 como workflow con ruteo fijo, sobre el golden set de tareas.

Pasos fijos, en código (no los decide el modelo), con los mismos componentes de semana 10:
1. Ruteo: `ruteo.clasificar` (Haiku 5.5 low, el prompt de la actividad 6 de semana 10) → sql, documental o mixta.
2. Ruta sql o mixta: la herramienta NLQ de semana 10 (Haiku 5.5 low, DDL legado + diccionario completo, abstención
   NO_SQL) genera UNA consulta por clave de salida y se ejecuta una vez con la herramienta ejecutar_sql de semana 13
   (guard y transacción de solo lectura). Sin reintentos ni consulta de reglas, como en semana 10.
3. Ruta documental: semana 10 respondería con el índice documental, que no produce SQL ni cifras calculadas; para este
   golden set (todas las respuestas salen de la base) se registra como abstención.

Adaptaciones, para comparar solo la orquestación: la NLQ recibe la misma información de salida que el agente (la
descripción de cada clave y el contrato de forma, FORMA), y en tareas con varias claves se hace una llamada por clave.
El workflow no puede pedir aclaración: no tiene ese paso.
"""
import sys
import time
from pathlib import Path

AQUI = Path(__file__).resolve().parents[1]
REPO = AQUI.parent
sys.path.insert(0, str(AQUI))
sys.path.insert(0, str(REPO / "semana-10" / "experimentos"))

import ruteo  # noqa: E402
import sql_legado as sl  # noqa: E402

from agente.loop import FORMA, api_anthropic, costo  # noqa: E402

HAIKU = "claude-haiku-5-5"
ABSTENCION = ("\n\nIf the schema and dictionary do not contain the data the question asks for (for example service "
              "levels, freight rates, policies, approvals, warehouse layouts or documents), do not approximate it with "
              "other columns: output exactly NO_SQL instead of a query.")  # idéntico a semana-10/experimentos/asistente.py
SIS_NLQ = sl.sistema("\n".join(sl.DDL_LEGADO[t] for t in sl.DICCIONARIO), sl.texto_diccionario(list(sl.DICCIONARIO))) + ABSTENCION


def nlq(pregunta: str):
    t0 = time.perf_counter()
    d = api_anthropic({"model": HAIKU, "max_tokens": 8000, "system": SIS_NLQ, "output_config": {"effort": "low"},
                       "messages": [{"role": "user", "content": pregunta}]})
    texto = "".join(b.get("text", "") for b in d["content"] if b.get("type") == "text")
    u = d["usage"]
    return texto, u["input_tokens"], u["output_tokens"], time.perf_counter() - t0


def resolver(tarea: dict, h) -> dict:
    """Devuelve el mismo formato que el agente: estado, final (RespuestaFinal), pasos, tokens, costo, segundos."""
    t0 = time.perf_counter()
    r = ruteo.clasificar(HAIKU, "low", tarea["tarea"])
    tin, tout, llamadas, pasos = r["tokens_in"], r["tokens_out"], [], 1
    ruta = r["ruta"] or "sql"
    if ruta == "documental":
        final = {"estado": "abstenida", "respuesta": "Ruta documental: el workflow no calcula cifras sobre la base para esta pregunta.",
                 "resultados": [], "evidencia": [], "supuestos": [], "pregunta_aclaracion": None}
        estado = "abstenida"
    else:
        resultados, abstuvo = [], False
        salida = tarea.get("salida") or {"respuesta": {"descripcion": "the answer", "tipo": "filas"}}
        for clave, s in salida.items():
            pregunta = (tarea["tarea"] + f"\n\nReturn only: {s['descripcion']} ({s['tipo']}).\n\n" + FORMA)
            texto, i, o, _ = nlq(pregunta)
            tin, tout, pasos = tin + i, tout + o, pasos + 1
            if texto.strip().upper().startswith("NO_SQL"):
                abstuvo = True
                break
            consulta = sl.re7.extraer_sql(texto)
            if consulta is None:
                continue
            res = h.llamar("ejecutar_sql", {"sql": consulta, "max_filas": 200})
            llamadas.append({"clave": clave, "ok": res["ok"], "error": (res.get("error") or {}).get("tipo")})
            valor = [f if len(f) > 1 else f[0] for f in res["filas"]] if res["ok"] else None
            if res["ok"] and len(res["filas"]) == 1 and len(res["filas"][0]) == 1:
                valor = res["filas"][0][0]
            resultados.append({"clave": clave, "sql": consulta, "valor": valor})
        if abstuvo:
            estado = "abstenida"
            final = {"estado": estado, "respuesta": "NO_SQL: los datos no están en el esquema.", "resultados": [],
                     "evidencia": [], "supuestos": [], "pregunta_aclaracion": None}
        else:
            estado = "respondida"
            final = {"estado": estado, "respuesta": "", "resultados": resultados if tarea.get("salida") else [],
                     "evidencia": [], "supuestos": [], "pregunta_aclaracion": None}
    return {"estado": estado, "final": final, "ruta": ruta, "pasos": pasos, "herramientas": len(llamadas),
            "errores_herramienta": sum(not x["ok"] for x in llamadas), "tokens_in": tin, "tokens_out": tout,
            "costo_usd": costo(HAIKU, tin, tout), "segundos": round(time.perf_counter() - t0, 2)}
