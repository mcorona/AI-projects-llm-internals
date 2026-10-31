"""Semana 14, actividad 3: transporte Streamable HTTP (protocolo 2026-07-28) en 127.0.0.1.

Capas, de afuera hacia adentro:

1. `Frontera` (ASGI propio):
   - tamaño máximo del cuerpo (413, antes de leerlo completo);
   - peticiones concurrentes en curso (503 con Retry-After si se excede, en vez de encolar sin límite);
   - una traza JSONL por petición: método, herramienta o URI, sujeto, scopes, cliente, protocolo, estado HTTP,
     resultado, latencia y bytes. Nunca registra argumentos, resultados ni encabezados de autorización.
2. App Streamable HTTP del SDK (`Server.streamable_http_app`):
   - `Host` y `Origin` contra listas permitidas (DNS rebinding: 403 con Origin hostil);
   - `MCP-Protocol-Version`, `Mcp-Method` y `Mcp-Name` contra el cuerpo (400 `HeaderMismatch`, -32020). La frontera
     agrega el caso que el SDK no cubre: encabezado de una versión con handshake y `_meta` de 2026-07-28;
   - sin sesiones: 2026-07-28 es sin estado y `stateless_http=True` cubre también a clientes de versiones previas;
   - respuestas JSON (`json_response=True`); GET y DELETE se responden 405 en la frontera.
3. Servidor de primitivas (actividad 2) con tiempo límite y concurrencia por llamada a herramienta.

El sujeto y los scopes de la traza los da `identidad(scope)`: en esta actividad es el usuario fijo del proceso sin scopes;
en la actividad 5 salen del token OAuth validado.
"""
from __future__ import annotations

import json
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from mcp.server.lowlevel import Server
from mcp.server.transport_security import TransportSecuritySettings

HOST = "127.0.0.1"  # fijo: el servidor nunca escucha en otras interfaces (amenaza A08)
RUTA = "/mcp"


@dataclass
class LimitesHTTP:
    max_cuerpo_bytes: int = 256 * 1024     # una petición MCP legítima de estas herramientas pesa < 10 KB
    max_en_curso: int = 16                 # peticiones HTTP simultáneas; más allá, 503


@dataclass
class Trazas:
    """Escribe una línea JSON por petición. Thread-safe; `None` desactiva el archivo pero conserva `ultimas` en memoria."""
    ruta: Path | None = None
    ultimas: list = field(default_factory=list)
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def escribir(self, registro: dict) -> None:
        linea = json.dumps(registro, ensure_ascii=False, default=str)
        with self._lock:
            self.ultimas.append(registro)
            del self.ultimas[:-1000]
            if self.ruta is not None:
                self.ruta.parent.mkdir(parents=True, exist_ok=True)
                with self.ruta.open("a", encoding="utf-8") as f:
                    f.write(linea + "\n")


def _identidad_fija(usuario: str) -> Callable[[dict], tuple[str, list[str]]]:
    return lambda scope: (usuario, [])


def _resumen_peticion(cuerpo: bytes) -> dict:
    try:
        msg = json.loads(cuerpo)
    except (ValueError, UnicodeDecodeError):
        return {"metodo": None, "nombre": None, "id": None, "cliente": None, "protocolo": None}
    if not isinstance(msg, dict):
        return {"metodo": None, "nombre": None, "id": None, "cliente": None, "protocolo": None}
    params = msg.get("params") if isinstance(msg.get("params"), dict) else {}
    meta = params.get("_meta") if isinstance(params.get("_meta"), dict) else {}
    cliente = meta.get("io.modelcontextprotocol/clientInfo") or params.get("clientInfo") or {}
    return {"metodo": msg.get("method"), "nombre": params.get("name") or params.get("uri"), "id": msg.get("id"),
            "cliente": cliente.get("name") if isinstance(cliente, dict) else None,
            "protocolo": meta.get("io.modelcontextprotocol/protocolVersion") or params.get("protocolVersion")}


def _resultado(estado: int, tipo: str, cuerpo: bytes) -> tuple[str, str | None]:
    """Clasifica la respuesta: ok, error_herramienta (isError), error_protocolo (JSON-RPC error, 400 o 200) o rechazado
    (estado HTTP de transporte: Origin, Host, método, tamaño o concurrencia)."""
    if estado == 202:
        return "aceptado", None
    if estado >= 400 and estado != 400:  # 403, 405, 413, 421, 503...: rechazo de transporte, antes del protocolo
        return "rechazado", str(estado)
    if estado >= 400 and not cuerpo.strip().startswith(b"{"):
        return "rechazado", str(estado)
    if "application/json" not in tipo:
        return ("ok" if estado < 400 else "rechazado"), None
    try:
        msg = json.loads(cuerpo)
    except ValueError:
        return "rechazado", str(estado)
    if isinstance(msg, dict) and "error" in msg:
        return "error_protocolo", str(msg["error"].get("code"))
    res = msg.get("result", {}) if isinstance(msg, dict) else {}
    if isinstance(res, dict) and res.get("isError"):
        error = (res.get("structuredContent") or {}).get("error") or {}
        return "error_herramienta", error.get("tipo")
    return ("ok" if estado < 400 else "rechazado"), None


async def _responder(send, estado: int, cuerpo: dict | str, extra: list[tuple[bytes, bytes]] = ()):
    datos = (json.dumps(cuerpo) if isinstance(cuerpo, dict) else cuerpo).encode()
    tipo = b"application/json" if isinstance(cuerpo, dict) else b"text/plain; charset=utf-8"
    await send({"type": "http.response.start", "status": estado,
                "headers": [(b"content-type", tipo), (b"content-length", str(len(datos)).encode()), *extra]})
    await send({"type": "http.response.body", "body": datos})


class Frontera:
    """Límites de tamaño y concurrencia, y trazas JSONL, alrededor de la app ASGI del SDK."""

    def __init__(self, app, limites: LimitesHTTP, trazas: Trazas, identidad: Callable[[dict], tuple[str, list[str]]],
                 autorizador=None):
        self.app, self.limites, self.trazas, self.identidad = app, limites, trazas, identidad
        self.autorizador = autorizador   # actividad 5: OAuth (servidor/oauth.py); None = usuario fijo del proceso
        self.en_curso = 0
        self._lock = threading.Lock()

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":   # lifespan: arranque y cierre del administrador de sesiones del SDK
            return await self.app(scope, receive, send)
        inicio = time.perf_counter()
        sujeto, scopes = (None, []) if self.autorizador else self.identidad(scope)
        registro = {"ts": round(time.time(), 3), "http": scope["method"], "ruta": scope["path"], "sujeto": sujeto,
                    "scopes": scopes}

        # 1. Cuerpo con límite (se rechaza en cuanto se pasa, sin terminar de leerlo)
        cuerpo, demasiado = bytearray(), False
        largo = dict(scope["headers"]).get(b"content-length")
        if largo is not None and largo.isdigit() and int(largo) > self.limites.max_cuerpo_bytes:
            demasiado = True
        else:
            while True:
                m = await receive()
                if m["type"] != "http.request":
                    break
                cuerpo += m.get("body", b"")
                if len(cuerpo) > self.limites.max_cuerpo_bytes:
                    demasiado = True
                    break
                if not m.get("more_body"):
                    break
        registro |= _resumen_peticion(bytes(cuerpo)) if not demasiado else {"metodo": None, "nombre": None}
        registro["bytes_in"] = len(cuerpo)

        captura = {"estado": 0, "tipo": "", "cuerpo": bytearray()}

        async def send_traza(m):
            if m["type"] == "http.response.start":
                captura["estado"] = m["status"]
                captura["tipo"] = dict(m.get("headers", [])).get(b"content-type", b"").decode()
            elif m["type"] == "http.response.body" and len(captura["cuerpo"]) < 1_000_000:
                captura["cuerpo"] += m.get("body", b"")
            await send(m)

        try:
            es_mcp = scope["path"] == RUTA
            if es_mcp and scope["method"] != "POST":
                # 2026-07-28 no tiene flujo GET ni DELETE de sesión: SHOULD 405 (transports/streamable-http)
                await _responder(send_traza, 405, "Method Not Allowed", [(b"allow", b"POST")])
                return
            if demasiado:
                await _responder(send_traza, 413, {"jsonrpc": "2.0", "id": None, "error": {
                    "code": -32600, "message": f"Request body too large (max {self.limites.max_cuerpo_bytes} bytes)"}})
                return
            # OAuth (actividad 5): token válido y scopes suficientes para la operación del cuerpo, antes de todo lo demás
            if es_mcp and self.autorizador is not None:
                at, rechazo = await self.autorizador.evaluar(dict(scope["headers"]), registro.get("metodo"),
                                                             registro.get("nombre"))
                if at is not None:
                    registro |= {"sujeto": at.subject, "scopes": sorted(at.scopes), "cliente_oauth": at.client_id}
                if rechazo is not None:
                    registro["motivo_auth"] = rechazo.motivo
                    await _responder(send_traza, rechazo.estado, rechazo.cuerpo,
                                     [(b"www-authenticate", rechazo.www_authenticate.encode())])
                    return
            # El SDK enruta por el encabezado: con una versión con handshake no compara contra el `_meta` del cuerpo.
            # La especificación 2026-07-28 exige rechazar si el encabezado no coincide con el `_meta` (HeaderMismatch).
            version_h = dict(scope["headers"]).get(b"mcp-protocol-version", b"").decode()
            if registro.get("protocolo") and version_h and version_h != registro["protocolo"] \
                    and registro["protocolo"] == "2026-07-28":
                await _responder(send_traza, 400, {"jsonrpc": "2.0", "id": registro.get("id"), "error": {
                    "code": -32020, "message": "Header mismatch: MCP-Protocol-Version does not match _meta protocolVersion"}})
                return
            # 2. Concurrencia: rechazo inmediato con 503 en vez de una cola sin límite
            with self._lock:
                lleno = self.en_curso >= self.limites.max_en_curso
                if not lleno:
                    self.en_curso += 1
            if lleno:
                await _responder(send_traza, 503, {"jsonrpc": "2.0", "id": registro.get("id"), "error": {
                    "code": -32000, "message": "Server busy, retry later"}}, [(b"retry-after", b"1")])
                return
            try:
                entregado = False

                async def receive_reemplazo():
                    nonlocal entregado
                    if not entregado:
                        entregado = True
                        return {"type": "http.request", "body": bytes(cuerpo), "more_body": False}
                    return await receive()
                await self.app(scope, receive_reemplazo, send_traza)
            finally:
                with self._lock:
                    self.en_curso -= 1
        finally:
            resultado, error = _resultado(captura["estado"], captura["tipo"], bytes(captura["cuerpo"]))
            registro |= {"estado": int(captura["estado"]), "resultado": resultado, "error": error,
                         "ms": round(1000 * (time.perf_counter() - inicio), 1), "bytes_out": len(captura["cuerpo"])}
            self.trazas.escribir(registro)


def seguridad_transporte(puerto: int) -> TransportSecuritySettings:
    """Solo el propio servidor en loopback: Host y Origin exactos para el puerto (amenaza A08)."""
    return TransportSecuritySettings(
        enable_dns_rebinding_protection=True,
        allowed_hosts=[f"127.0.0.1:{puerto}", f"localhost:{puerto}"],
        allowed_origins=[f"http://127.0.0.1:{puerto}", f"http://localhost:{puerto}"])


def crear_app(servidor: Server, puerto: int, *, usuario: str = "analista", limites: LimitesHTTP | None = None,
              trazas: Trazas | None = None, identidad=None, verificador=None, emisor: str | None = None,
              recurso: str | None = None):
    """Sin `verificador`: usuario fijo del proceso (actividad 3). Con `verificador` (servidor/oauth.py): resource server
    OAuth con Protected Resource Metadata (RFC 9728), validación del token en la frontera y de nuevo en el SDK."""
    limites = limites or LimitesHTTP()
    auth = autorizador = None
    if verificador is not None:
        from mcp.server.auth.routes import build_resource_metadata_url
        from mcp.server.auth.settings import AuthSettings

        from .oauth import SCOPE_BASE, Autorizador
        recurso = recurso or f"http://{HOST}:{puerto}{RUTA}"
        auth = AuthSettings(issuer_url=emisor, resource_server_url=recurso, validate_token_resource=True,
                            required_scopes=[SCOPE_BASE])
        autorizador = Autorizador(verificador, str(build_resource_metadata_url(auth.resource_server_url)))
    app = servidor.streamable_http_app(streamable_http_path=RUTA, json_response=True, stateless_http=True,
                                       transport_security=seguridad_transporte(puerto),
                                       max_request_body_size=limites.max_cuerpo_bytes, host=HOST,
                                       auth=auth, token_verifier=verificador)
    return Frontera(app, limites, trazas or Trazas(), identidad or _identidad_fija(usuario), autorizador)


def correr(servidor: Server, puerto: int, *, usuario: str, ruta_trazas: Path | None, limites: LimitesHTTP | None = None,
           **oauth):
    import uvicorn
    app = crear_app(servidor, puerto, usuario=usuario, limites=limites, trazas=Trazas(ruta_trazas), **oauth)
    uvicorn.run(app, host=HOST, port=puerto, log_level="warning", proxy_headers=False, server_header=False)
