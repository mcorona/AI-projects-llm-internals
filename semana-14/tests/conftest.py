import asyncio
import os
import sys
from pathlib import Path

import pytest

S14 = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(S14))
sys.path.insert(0, str(S14.parent / "semana-13"))

from herramientas import Contexto, Herramientas  # noqa: E402

HAY_BASE = bool(os.environ.get("NLQ_LEGADO_DSN") or os.environ.get("PG_ADMIN_DSN") or os.environ.get("PG_DSN"))
USUARIOS = ("analista", "almacenista", "vendedor")


@pytest.fixture(scope="session")
def conexion():
    if not HAY_BASE:
        pytest.skip("sin base de datos (define PG_ADMIN_DSN, NLQ_LEGADO_DSN o PG_DSN)")
    from herramientas.conexion import conectar
    conn, _ = conectar()
    yield conn
    conn.close()


def con_cliente(servidor, fn):
    """Corre `fn(cliente)` con un cliente MCP en memoria (protocolo 2026-07-28) contra `servidor`."""
    from mcp import Client

    async def _correr():
        async with Client(servidor) as c:
            return await fn(c)
    try:
        return asyncio.run(_correr())
    except BaseExceptionGroup as g:  # el cliente corre en un task group de anyio: se propaga el error de protocolo
        hojas = []

        def _hojas(e):
            for x in e.exceptions:
                _hojas(x) if isinstance(x, BaseExceptionGroup) else hojas.append(x)
        _hojas(g)
        if len(hojas) == 1:
            raise hojas[0] from None
        raise


def fabrica(usuario, conexion=None, idioma="es"):
    """Una sola instancia por servidor, como en un proceso real (la bitácora y las propuestas son del contexto)."""
    h = Herramientas(Contexto.de_usuario(usuario, conexion=conexion, idioma=idioma))
    return lambda: h


class ServidorHTTP:
    """Uvicorn real en 127.0.0.1 con un puerto libre, en un hilo (para probar con el cliente HTTP del SDK)."""

    def __init__(self, servidor_mcp, **kw):
        import socket
        import threading
        import time

        import uvicorn
        from servidor.http import HOST, Trazas, crear_app

        with socket.socket() as s:
            s.bind((HOST, 0))
            self.puerto = s.getsockname()[1]
        self.trazas = kw.pop("trazas", None) or Trazas()
        self.app = crear_app(servidor_mcp, self.puerto, trazas=self.trazas, **kw)
        self.server = uvicorn.Server(uvicorn.Config(self.app, host=HOST, port=self.puerto, log_level="error",
                                                    lifespan="on"))
        self.hilo = threading.Thread(target=self.server.run, daemon=True)
        self.hilo.start()
        fin = time.time() + 10
        while not self.server.started:
            if time.time() > fin:
                raise RuntimeError("uvicorn no arrancó")
            time.sleep(0.02)
        self.url = f"http://{HOST}:{self.puerto}/mcp"

    def direcciones(self):
        return [sock.getsockname() for srv in self.server.servers for sock in srv.sockets]

    def cerrar(self):
        self.server.should_exit = True
        self.hilo.join(timeout=10)

    def __enter__(self):
        return self

    def __exit__(self, *a):
        self.cerrar()
