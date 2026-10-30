"""Servidor MCP de la semana 14 sobre la base legada, por stdio o por Streamable HTTP en 127.0.0.1.

    python -m servidor --transporte stdio --usuario analista
    python -m servidor --transporte http --puerto 8014 --usuario analista --trazas resultados/trazas/http.jsonl
    python -m servidor --transporte http --oauth --trazas resultados/trazas/oauth.jsonl     # actividad 5

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


def servidor_oauth(a):
    """Servidor de la actividad 5: JWKS del emisor (discovery), pool de conexiones y roles de base por perfil."""
    import json
    import urllib.request

    from .oauth import PoolConexiones, VerificadorJWT, aplicar_roles_bd, fabrica_oauth
    with urllib.request.urlopen(f"{a.emisor}/.well-known/openid-configuration", timeout=10) as r:
        meta = json.load(r)
    if meta["issuer"] != a.emisor:
        raise SystemExit(f"el emisor del discovery {meta['issuer']!r} no es {a.emisor!r}")
    recurso = f"http://127.0.0.1:{a.puerto}/mcp"
    pool = None
    if any(os.environ.get(v) for v in ("NLQ_LEGADO_DSN", "PG_ADMIN_DSN")):
        from herramientas.conexion import conectar
        conn, _ = conectar()              # crea copilot_nlq si hace falta y fija NLQ_LEGADO_DSN
        conn.close()
        if os.environ.get("PG_ADMIN_DSN"):
            aplicar_roles_bd(os.environ["PG_ADMIN_DSN"])
        pool = PoolConexiones(os.environ["NLQ_LEGADO_DSN"], tamano=4)
    verificador = VerificadorJWT(a.emisor, recurso, meta["jwks_uri"])
    return crear_servidor(fabrica_oauth(pool, a.idioma)), {"verificador": verificador, "emisor": a.emisor,
                                                           "recurso": recurso}


def main():
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--transporte", choices=["stdio", "http"], default="stdio")
    p.add_argument("--usuario", default=os.environ.get("MCP_USUARIO", "analista"))
    p.add_argument("--idioma", choices=["es", "en"], default=os.environ.get("MCP_IDIOMA", "es"))
    p.add_argument("--puerto", type=int, default=8014)
    p.add_argument("--trazas", type=Path, default=None, help="archivo JSONL de trazas por petición (solo http)")
    p.add_argument("--oauth", action="store_true", help="resource server OAuth: el usuario y los permisos salen del token")
    p.add_argument("--emisor", default=os.environ.get("OAUTH_EMISOR", "http://127.0.0.1:8180/realms/legacybridge"))
    a = p.parse_args()
    if a.oauth and a.transporte == "http":
        servidor, extra = servidor_oauth(a)
        from .http import correr
        print(f"[servidor] http://127.0.0.1:{a.puerto}/mcp con OAuth (emisor {a.emisor})", file=sys.stderr)
        return correr(servidor, a.puerto, usuario="", ruta_trazas=a.trazas, **extra)
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
