"""Semana 13, actividad 3: loop agéntico propio con tool use de la API de Anthropic.

El modelo pide herramientas; el sistema las ejecuta (las de la actividad 2) y le devuelve los resultados, hasta que
el modelo entrega la respuesta final con la herramienta `responder` o se alcanza un límite.

- Llamadas paralelas: si el modelo pide varias herramientas en un mismo turno, se ejecutan todas y sus resultados se
  devuelven juntos en un solo mensaje (como pide la API). Se ejecutan en orden porque comparten la conexión a la base.
- Reintento acotado: un error de herramienta vuelve al modelo como tool_result con is_error y la sugerencia, para que
  corrija. Con MAX_ERRORES_SEGUIDOS errores consecutivos el loop para con estado limite_alcanzado. Los errores
  transitorios de la API (429, 5xx, 529) se reintentan con espera exponencial.
- Parada con estado: respondida, requiere_aclaracion o abstenida (los elige el modelo); limite_alcanzado (pasos,
  llamadas, tokens, tiempo o errores) o error (API) los pone el sistema.
- Respuesta final estructurada: `responder` usa el JSON Schema de RespuestaFinal (Pydantic); si no valida, el error
  vuelve al modelo como cualquier otro.
- Trazas JSONL por paso: un evento por llamada al modelo, por herramienta, por la respuesta final y por la parada.
"""
from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request
import uuid
from dataclasses import dataclass, field
from pathlib import Path

from pydantic import ValidationError

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from agente.respuesta import RespuestaFinal, herramienta_responder  # noqa: E402
from herramientas import Herramientas, definiciones  # noqa: E402

RAIZ = Path(__file__).resolve().parents[2]
PRECIOS = json.loads((RAIZ / "semana-07" / "prices.json").read_text(encoding="utf-8"))
MAX_ERRORES_SEGUIDOS = 3

SISTEMA = """You are a data analyst for a distribution company. You answer business questions over a legacy inventory \
database whose tables and columns have cryptic names, using only the tools provided.

How to work:
- Call describir_esquema before writing SQL. Never guess table or column names.
- When the task uses a business term (coverage, at risk, escalation level, reorder point, proposal, approval, surplus, \
class A, open order...), call buscar_regla_negocio and apply the definition exactly as written, including the cutoff \
date convention. Do not invent your own definition.
- Before filtering by a text or code (country, city, category, status), check how it is stored with muestrear_valores.
- Run queries with ejecutar_sql. If a tool returns an error, read its suggestion and fix the call.
- You may request several independent tools in the same turn.
- Finish by calling responder exactly once, alone:
  - estado "respondida": one resultado per output key listed in the task, each with the single SELECT whose result is \
exactly that value (it will be re-executed to check it), and the value.
  - estado "requiere_aclaracion": the request is ambiguous (missing item, period, place or criterion); ask one question.
  - estado "abstenida": the database does not contain the data needed (for example prices, customers, deliveries, \
transfers); explain what is missing. Never approximate with other columns.
- Write the answer in the language of the task. List any assumption you made."""


@dataclass
class Limites:
    max_pasos: int = 12            # llamadas al modelo
    max_herramientas: int = 30     # ejecuciones de herramientas
    max_tokens_total: int = 200_000
    max_segundos: float = 180.0
    max_tokens_salida: int = 4000


@dataclass
class Resultado:
    estado: str
    final: dict | None
    pasos: int
    herramientas: int
    tokens_in: int
    tokens_out: int
    costo_usd: float
    segundos: float
    motivo: str = ""
    corrida: str = ""
    errores_herramienta: int = 0
    turnos_paralelos: int = 0


def api_anthropic(cuerpo: dict, reintentos: int = 4) -> dict:
    req = urllib.request.Request("https://api.anthropic.com/v1/messages", data=json.dumps(cuerpo).encode(),
                                 headers={"content-type": "application/json", "anthropic-version": "2023-06-01",
                                          "x-api-key": os.environ["ANTHROPIC_API_KEY"]})
    for intento in range(reintentos):
        try:
            with urllib.request.urlopen(req, timeout=180) as r:
                return json.loads(r.read())
        except urllib.error.HTTPError as e:
            if e.code in (429, 500, 502, 503, 529) and intento < reintentos - 1:
                time.sleep(2 ** (intento + 1))
                continue
            raise RuntimeError(f"API HTTP {e.code}: {e.read().decode()[:300]}") from None
        except urllib.error.URLError:
            if intento < reintentos - 1:
                time.sleep(2 ** (intento + 1))
                continue
            raise
    raise RuntimeError("API sin respuesta")


def costo(modelo: str, tin: int, tout: int) -> float:
    p = PRECIOS[f"anthropic:{modelo}"]
    return (tin * p["in"] + tout * p["out"]) / 1e6


def revisar_final(final: dict, tarea: dict) -> str:
    """Reglas que el JSON Schema no expresa porque dependen de la tarea. Devuelve el problema o cadena vacía."""
    texto = json.dumps(final, ensure_ascii=False)
    if "<parameter" in texto or "</" + "respuesta>" in texto:
        return ("A field contains serialized parameters (for example '<parameter name=...>'): send each field as its own "
                "JSON property, with resultados as a list.")
    claves = set(tarea.get("salida", {}))
    reportadas = [x["clave"] for x in final["resultados"]]
    if final["estado"] == "respondida" and claves:
        faltan, sobran = claves - set(reportadas), set(reportadas) - claves
        if faltan or sobran or len(reportadas) != len(set(reportadas)):
            return (f"resultados must have exactly one entry per output key {sorted(claves)}; "
                    f"missing {sorted(faltan)}, unexpected {sorted(sobran)}.")
    if final["estado"] == "requiere_aclaracion" and not final.get("pregunta_aclaracion"):
        return "pregunta_aclaracion is required when estado is 'requiere_aclaracion'."
    return ""


def mensaje_tarea(tarea: dict) -> str:
    texto = tarea["tarea"]
    if tarea.get("salida"):
        claves = "\n".join(f"- {c}: {s['descripcion']} ({s['tipo']})" for c, s in tarea["salida"].items())
        texto += "\n\nOutput keys to report if you can answer:\n" + claves
    return texto


class Agente:
    def __init__(self, herramientas: Herramientas, modelo: str = "claude-haiku-5-5", esfuerzo: str = "low",
                 limites: Limites | None = None, api=api_anthropic, trazas: Path | None = None):
        self.h, self.modelo, self.esfuerzo = herramientas, modelo, esfuerzo
        self.lim = limites or Limites()
        self.api, self.trazas = api, trazas
        # El catálogo viene de la fuente de herramientas: nativo (definiciones()) o el que anuncia el servidor MCP.
        self.tools = (herramientas.definiciones() if hasattr(herramientas, "definiciones") else definiciones()) + [herramienta_responder()]

    def _traza(self, evento: dict):
        if self.trazas:
            self.trazas.parent.mkdir(parents=True, exist_ok=True)
            with open(self.trazas, "a", encoding="utf-8") as f:
                f.write(json.dumps({"ts": round(time.time(), 3), **evento}, ensure_ascii=False, default=str) + "\n")

    def resolver(self, tarea: dict) -> Resultado:
        corrida = uuid.uuid4().hex[:12]
        tid = tarea.get("id", "")
        mensajes = [{"role": "user", "content": mensaje_tarea(tarea)}]
        r = Resultado("error", None, 0, 0, 0, 0, 0.0, 0.0, corrida=corrida)
        t0 = time.perf_counter()
        errores_seguidos, recordatorio = 0, False

        def parar(estado, motivo, final=None):
            r.estado, r.motivo, r.final = estado, motivo, final
            r.segundos = round(time.perf_counter() - t0, 2)
            self._traza({"corrida": corrida, "tarea": tid, "tipo": "parada", "estado": estado, "motivo": motivo,
                         "pasos": r.pasos, "herramientas": r.herramientas, "tokens_in": r.tokens_in,
                         "tokens_out": r.tokens_out, "costo_usd": round(r.costo_usd, 6), "segundos": r.segundos})
            return r

        while True:
            if r.pasos >= self.lim.max_pasos:
                return parar("limite_alcanzado", "max_pasos")
            if r.tokens_in + r.tokens_out >= self.lim.max_tokens_total:
                return parar("limite_alcanzado", "max_tokens_total")
            if time.perf_counter() - t0 >= self.lim.max_segundos:
                return parar("limite_alcanzado", "max_segundos")
            cuerpo = {"model": self.modelo, "max_tokens": self.lim.max_tokens_salida, "system": SISTEMA,
                      "tools": self.tools, "messages": mensajes, "output_config": {"effort": self.esfuerzo}}
            t1 = time.perf_counter()
            try:
                d = self.api(cuerpo)
            except Exception as e:  # noqa: BLE001
                return parar("error", f"api: {e}")
            r.pasos += 1
            u = d.get("usage", {})
            tin, tout = u.get("input_tokens", 0), u.get("output_tokens", 0)
            r.tokens_in += tin
            r.tokens_out += tout
            r.costo_usd += costo(self.modelo, tin, tout)
            bloques = d.get("content", [])
            usos = [b for b in bloques if b.get("type") == "tool_use"]
            self._traza({"corrida": corrida, "tarea": tid, "tipo": "modelo", "paso": r.pasos, "modelo": self.modelo,
                         "esfuerzo": self.esfuerzo, "stop_reason": d.get("stop_reason"), "tokens_in": tin, "tokens_out": tout,
                         "costo_usd": round(costo(self.modelo, tin, tout), 6), "ms": round(1000 * (time.perf_counter() - t1)),
                         "herramientas_pedidas": [b["name"] for b in usos],
                         "texto": " ".join(b.get("text", "") for b in bloques if b.get("type") == "text")[:500]})
            mensajes.append({"role": "assistant", "content": bloques})

            if not usos:
                if d.get("stop_reason") == "max_tokens":
                    return parar("limite_alcanzado", "max_tokens_salida")
                if recordatorio:
                    return parar("limite_alcanzado", "sin_responder")
                recordatorio = True
                mensajes.append({"role": "user", "content": "Deliver your final answer by calling the responder tool."})
                continue

            if len(usos) > 1:
                r.turnos_paralelos += 1
            resultados, final = [], None
            for b in usos:
                if r.herramientas >= self.lim.max_herramientas:
                    return parar("limite_alcanzado", "max_herramientas")
                r.herramientas += 1
                t2 = time.perf_counter()
                if b["name"] == "responder":
                    try:
                        if len(usos) > 1:
                            raise ValueError("responder must be called alone, after the other tools have returned.")
                        final = RespuestaFinal.model_validate(b["input"]).model_dump()
                        problema = revisar_final(final, tarea)
                        if problema:
                            final = None
                            raise ValueError(problema)
                        salida = {"ok": True}
                    except (ValidationError, ValueError) as e:
                        msg = str(e) if isinstance(e, ValueError) and not isinstance(e, ValidationError) else \
                            "; ".join(f"{'.'.join(map(str, x['loc']))}: {x['msg']}" for x in e.errors())
                        salida = {"ok": False, "error": {"tipo": "respuesta_invalida", "mensaje": msg[:800],
                                                         "sugerencia": "Corrige los campos y llama responder de nuevo."}}
                else:
                    salida = self.h.llamar(b["name"], b.get("input") or {})
                ok = salida.get("ok", False)
                r.errores_herramienta += 0 if ok else 1
                errores_seguidos = 0 if ok else errores_seguidos + 1
                self._traza({"corrida": corrida, "tarea": tid, "tipo": "herramienta", "paso": r.pasos, "herramienta": b["name"],
                             "argumentos": b.get("input"), "ok": ok, "error": (salida.get("error") or {}).get("tipo"),
                             "paralela": len(usos) > 1, "ms": round(1000 * (time.perf_counter() - t2)),
                             "salida_chars": len(json.dumps(salida, ensure_ascii=False, default=str))})
                resultados.append({"type": "tool_result", "tool_use_id": b["id"], "is_error": not ok,
                                   "content": json.dumps(salida, ensure_ascii=False, default=str)})
            if final is not None:
                self._traza({"corrida": corrida, "tarea": tid, "tipo": "final", "paso": r.pasos, "respuesta": final})
                return parar(final["estado"], "responder", final)
            if errores_seguidos >= MAX_ERRORES_SEGUIDOS:
                return parar("limite_alcanzado", "errores_herramienta")
            mensajes.append({"role": "user", "content": resultados})
