"""Servidor MCP de la semana 14 sobre la base legada, por stdio o por Streamable HTTP en 127.0.0.1.

    python -m servidor --transporte stdio --usuario analista
    python -m servidor --transporte http --puerto 8014 --usuario analista --trazas resultados/trazas/http.jsonl

(desde `semana-14/`). Base de datos: NLQ_LEGADO_DSN, PG_ADMIN_DSN o PG_DSN (herramientas/conexion.py de la semana 13);
sin ninguna, las herramientas que no la necesitan funcionan y las demás devuelven `sin_base`.
El usuario lo fija quien arranca el proceso, nunca el modelo; en la actividad 5 lo reemplaza el token OAuth.
"""
import argparse
import asyncio
import os
import sys
from pathlib import Path

from .primitivas import crear_servidor  # agrega semana-13 a sys.path

from herramientas import Contexto, Herramientas  # noqa: E402


def herramientas_de(usuario: str, idioma: str):
    conn = None
    if any(os.environ.get(v) for v in ("NLQ_LEGADO_DSN", "PG_ADMIN_DSN", "PG_DSN")):
        from herramientas.conexion import conectar
        conn, rol = conectar()
        print(f"[servidor] usuario {usuario}, rol de base {rol}", file=sys.stderr)
    else:
        print(f"[servidor] usuario {usuario}, sin base de datos", file=sys.stderr)
    h = Herramientas(Contexto.de_usuario(usuario, conexion=conn, idioma=idioma))
    return lambda: h


def main():
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--transporte", choices=["stdio", "http"], default="stdio")
    p.add_argument("--usuario", default=os.environ.get("MCP_USUARIO", "analista"))
    p.add_argument("--idioma", choices=["es", "en"], default=os.environ.get("MCP_IDIOMA", "es"))
    p.add_argument("--puerto", type=int, default=8014)
    p.add_argument("--trazas", type=Path, default=None, help="archivo JSONL de trazas por petición (solo http)")
    a = p.parse_args()
    servidor = crear_servidor(herramientas_de(a.usuario, a.idioma))
    if a.transporte == "stdio":
        from mcp.server.stdio import stdio_server

        async def _stdio():
            async with stdio_server() as (lectura, escritura):
                await servidor.run(lectura, escritura, servidor.create_initialization_options())
        asyncio.run(_stdio())
    else:
        from .http import correr
        print(f"[servidor] http://127.0.0.1:{a.puerto}/mcp", file=sys.stderr)
        correr(servidor, a.puerto, usuario=a.usuario, ruta_trazas=a.trazas)


if __name__ == "__main__":
    main()
