"""Semana 13, actividad 10: agente con el Claude Agent SDK (claude-agent-sdk), con las mismas herramientas.

Lo que cambia frente al loop propio (agente/loop.py) es solo la orquestación: el loop, los reintentos y la parada los
maneja el SDK (que corre el CLI de Claude Code incluido en el paquete). Lo que se mantiene igual:
- Herramientas: las mismas seis (`definiciones()`), con los mismos JSON Schema, servidas en proceso con
  `create_sdk_mcp_server`; cada llamada ejecuta `Herramientas.llamar`, así que guard, permisos y errores son los mismos.
- Respuesta final: la herramienta `responder` con el JSON Schema de RespuestaFinal y la misma `revisar_final`.
- Prompt de sistema y mensaje de la tarea: los mismos (SISTEMA y mensaje_tarea, con el contrato de forma).
- Modelo y límites: Haiku 5.5, esfuerzo low, 12 turnos como máximo y un tope de costo por tarea.

Aislamiento: `tools=[]` desactiva todas las herramientas integradas de Claude Code (Bash, Read, Write, Web...),
`setting_sources=[]` no carga configuración del usuario ni del proyecto (CLAUDE.md, .mcp.json, permisos), el directorio
de trabajo es uno temporal vacío y solo las herramientas del servidor `legado` están permitidas.
"""
import asyncio
import json
import tempfile
import time
import uuid
from pathlib import Path

from claude_agent_sdk import (AssistantMessage, ClaudeAgentOptions, ResultMessage, ToolUseBlock, create_sdk_mcp_server,
                              query, tool)

from agente.loop import SISTEMA, Limites, Resultado, costo, mensaje_tarea, revisar_final
from agente.respuesta import RespuestaFinal, herramienta_responder
from herramientas import definiciones

SERVIDOR = "legado"
PREFIJO = f"mcp__{SERVIDOR}__"
SISTEMA_SDK = SISTEMA + f"\n\nTool names carry the prefix {PREFIJO} (for example {PREFIJO}describir_esquema)."


def herramientas_sdk(h, tarea, eventos, estado, corrida="", tid=""):
    """Las seis herramientas más `responder`, como herramientas del SDK (mismos nombres, descripciones y esquemas)."""
    sdk_tools = []
    for d in definiciones() + [herramienta_responder()]:
        def fabricar(d):
            @tool(d["name"], d["description"], d["input_schema"])
            async def manejador(args):
                t0 = time.perf_counter()
                if d["name"] == "responder":
                    try:
                        final = RespuestaFinal.model_validate(args).model_dump()
                        problema = revisar_final(final, tarea)
                        if problema:
                            raise ValueError(problema)
                        estado["final"] = final
                        res = {"ok": True, "nota": "Answer recorded. Stop now, without any further text or tool calls."}
                    except Exception as e:  # noqa: BLE001
                        res = {"ok": False, "error": {"tipo": "respuesta_invalida", "mensaje": str(e)[:800],
                                                      "sugerencia": "Corrige los campos y llama responder de nuevo."}}
                else:
                    res = h.llamar(d["name"], args)
                eventos.append({"corrida": corrida, "tarea": tid, "tipo": "herramienta", "herramienta": d["name"],
                                "argumentos": args, "ok": res["ok"], "error": (res.get("error") or {}).get("tipo"),
                                "ms": round(1000 * (time.perf_counter() - t0)),
                                "salida_chars": len(json.dumps(res, ensure_ascii=False, default=str))})
                return {"content": [{"type": "text", "text": json.dumps(res, ensure_ascii=False, default=str)}],
                        "is_error": not res["ok"]}
            return manejador
        sdk_tools.append(fabricar(d))
    return sdk_tools


def servidor(h, tarea, eventos, estado, corrida, tid):
    """Servidor MCP en proceso del SDK con esas herramientas."""
    return create_sdk_mcp_server(name=SERVIDOR, version="0.1.0", tools=herramientas_sdk(h, tarea, eventos, estado, corrida, tid))


async def _resolver(h, tarea, modelo, esfuerzo, lim, tope_usd, trazas):
    corrida = uuid.uuid4().hex[:12]
    tid = tarea.get("id", "") + (f"#{tarea['rep']}" if "rep" in tarea else "")
    eventos, estado, usos = [], {"final": None}, []
    r = Resultado("error", None, 0, 0, 0, 0, 0.0, 0.0, corrida=corrida)
    t0 = time.perf_counter()
    nombres = [d["name"] for d in definiciones()] + ["responder"]
    with tempfile.TemporaryDirectory() as vacio:
        opciones = ClaudeAgentOptions(
            tools=[], allowed_tools=[PREFIJO + n for n in nombres], mcp_servers={SERVIDOR: servidor(h, tarea, eventos, estado, corrida, tid)},
            system_prompt=SISTEMA_SDK, model=modelo, effort=esfuerzo, max_turns=lim.max_pasos, max_budget_usd=tope_usd,
            setting_sources=[], cwd=vacio, permission_mode="dontAsk")
        resultado = None
        try:
            async for m in query(prompt=mensaje_tarea(tarea), options=opciones):
                if isinstance(m, AssistantMessage):
                    bloques = [b for b in m.content if isinstance(b, ToolUseBlock)]
                    usos += [b.name for b in bloques]
                    if len(bloques) > 1:
                        r.turnos_paralelos += 1
                    eventos.append({"corrida": corrida, "tarea": tid, "tipo": "modelo", "modelo": modelo, "esfuerzo": esfuerzo,
                                    "herramientas_pedidas": [b.name.removeprefix(PREFIJO) for b in bloques]})
                elif isinstance(m, ResultMessage):
                    resultado = m
        except Exception as e:  # noqa: BLE001
            r.motivo = f"sdk: {type(e).__name__}: {str(e)[:200]}"
    u = (resultado.usage or {}) if resultado else {}
    tin = u.get("input_tokens", 0) + u.get("cache_creation_input_tokens", 0) + u.get("cache_read_input_tokens", 0)
    r.tokens_in, r.tokens_out = tin, u.get("output_tokens", 0)
    r.costo_usd = (resultado.total_cost_usd if resultado and resultado.total_cost_usd is not None
                   else costo(modelo, r.tokens_in, r.tokens_out))
    r.pasos = resultado.num_turns if resultado else sum(e["tipo"] == "modelo" for e in eventos)
    llamadas = [e for e in eventos if e["tipo"] == "herramienta"]
    r.herramientas = len(llamadas)
    r.errores_herramienta = sum(not e["ok"] for e in llamadas)
    r.segundos = round(time.perf_counter() - t0, 2)
    rechazadas_sdk = max(0, len(usos) - len(llamadas))  # el SDK valida el esquema antes de llamar al manejador
    if estado["final"]:
        r.estado, r.final, r.motivo = estado["final"]["estado"], estado["final"], "responder"
    elif resultado is not None:
        r.estado = "limite_alcanzado"
        r.motivo = resultado.subtype if resultado.subtype != "success" else "sin_responder"
    eventos.append({"corrida": corrida, "tarea": tid, "tipo": "parada", "estado": r.estado, "motivo": r.motivo, "pasos": r.pasos,
                    "herramientas": r.herramientas, "rechazadas_por_esquema_sdk": rechazadas_sdk, "tokens_in": r.tokens_in,
                    "tokens_out": r.tokens_out, "costo_usd": round(r.costo_usd, 6), "costo_fuente": "sdk" if resultado else "tokens",
                    "segundos": r.segundos})
    if estado["final"]:
        eventos.insert(-1, {"corrida": corrida, "tarea": tid, "tipo": "final", "respuesta": estado["final"]})
    if trazas:
        from agente.loop import _CANDADO
        trazas.parent.mkdir(parents=True, exist_ok=True)
        with _CANDADO, open(trazas, "a", encoding="utf-8") as f:
            for e in eventos:
                f.write(json.dumps({"ts": round(time.time(), 3), **e}, ensure_ascii=False, default=str) + "\n")
    return r


class AgenteSDK:
    """Misma interfaz que agente.loop.Agente: resolver(tarea) -> Resultado."""
    def __init__(self, herramientas, modelo="claude-haiku-5-5", esfuerzo="low", limites: Limites | None = None,
                 trazas: Path | None = None, tope_usd: float = 0.05):
        self.h, self.modelo, self.esfuerzo, self.lim = herramientas, modelo, esfuerzo, limites or Limites()
        self.trazas, self.tope_usd = trazas, tope_usd

    def resolver(self, tarea: dict) -> Resultado:
        return asyncio.run(_resolver(self.h, tarea, self.modelo, self.esfuerzo, self.lim, self.tope_usd, self.trazas))
