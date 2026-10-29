"""Semana 13, actividad 4: servidor MCP (stdio) con el mismo catálogo de herramientas.

Expone las cinco herramientas de la actividad 2 con los mismos nombres, descripciones y JSON Schema
(`herramientas.definiciones()`), y ejecuta cada llamada con la misma implementación (`Herramientas.llamar`). Así el
servidor no duplica lógica: guard, permisos, límites y errores estructurados son los mismos.

Permisos: el usuario lo fija quien registra el servidor (el host: Claude Code, el agente o el inspector) con la variable
MCP_USUARIO (por defecto, analista), nunca el modelo. Los argumentos de las herramientas no admiten roles ni usuario.

Base de datos (herramientas/conexion.py): NLQ_LEGADO_DSN, o PG_ADMIN_DSN para recrear copilot_nlq, o PG_DSN
(copilot_ro). Sin ninguna, las herramientas que no necesitan base funcionan y las demás devuelven `sin_base`.

    MCP_USUARIO=analista python semana-13/servidor_mcp/servidor.py
"""
import asyncio
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import mcp_types as types  # noqa: E402
from mcp.server.lowlevel import Server  # noqa: E402
from mcp.server.stdio import stdio_server  # noqa: E402

from herramientas import Contexto, Herramientas, definiciones  # noqa: E402

USUARIO = os.environ.get("MCP_USUARIO", "analista")
IDIOMA = os.environ.get("MCP_IDIOMA", "es")
_h: Herramientas | None = None


def herramientas() -> Herramientas:
    global _h
    if _h is None:
        conn = None
        if any(os.environ.get(v) for v in ("NLQ_LEGADO_DSN", "PG_ADMIN_DSN", "PG_DSN")):
            from herramientas.conexion import conectar
            conn, rol = conectar()
            print(f"[servidor MCP] usuario {USUARIO}, rol de base {rol}", file=sys.stderr)
        else:
            print(f"[servidor MCP] usuario {USUARIO}, sin base de datos", file=sys.stderr)
        _h = Herramientas(Contexto.de_usuario(USUARIO, conexion=conn, idioma=IDIOMA))
    return _h


async def listar(ctx, params) -> types.ListToolsResult:
    return types.ListToolsResult(tools=[types.Tool(name=d["name"], description=d["description"], input_schema=d["input_schema"])
                                        for d in definiciones()])


async def llamar(ctx, params) -> types.CallToolResult:
    h = herramientas()
    res = h.llamar(params.name, params.arguments or {})
    del h.ctx.llamadas[:-200]  # la bitácora del proceso no crece sin límite
    return types.CallToolResult(content=[types.TextContent(type="text", text=json.dumps(res, ensure_ascii=False, default=str))],
                                structured_content=res, is_error=not res["ok"])


servidor = Server("legado-semana13", version="0.1.0",
                  instructions="Read-only tools over a legacy inventory schema: describe the schema, look up business "
                               "rules, sample values, validate and run SELECT queries.",
                  on_list_tools=listar, on_call_tool=llamar)


async def main():
    async with stdio_server() as (lectura, escritura):
        await servidor.run(lectura, escritura, servidor.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(main())
