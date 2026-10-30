"""Semana 14, actividad 5: el servidor MCP como resource server OAuth 2.1 con permisos mínimos.

Piezas:
- `VerificadorJWT`: firma por JWKS del emisor (con caché y rotación por `kid`), algoritmo fijo RS256 (sin `none` ni
  confusión HS/RS), `iss` y `aud` exactos, `exp` con margen, `sub` obligatorio y solo access tokens (`typ` Bearer).
- `Autorizador`: lo usa la frontera HTTP antes del SDK. 401 si no hay token o no es válido, 403 `insufficient_scope`
  si la operación pide scopes que el token no trae. Ambos con `WWW-Authenticate` que incluye `scope` y
  `resource_metadata` (el SDK no agrega `scope`, brecha de la actividad 1). El scope se decide por el cuerpo validado.
- `ContextoOAuth`: el Contexto de la semana 13 construido desde el token. Tablas, columnas y herramientas salen de los
  scopes (`auth/permisos_oauth.json`); los argumentos del modelo nunca cambian el usuario ni los permisos.
- `ConexionConRol` y `PoolConexiones`: cada consulta corre en una conexión propia del pool con `SET LOCAL ROLE` al rol
  de PostgreSQL del perfil (`auth/roles_bd.sql`). Si el guard fallara, la base niega igual (defensa en profundidad).
- `fabrica_oauth`: crea las herramientas de cada petición a partir del token que validó el SDK.

El token nunca sale del servidor: no se reenvía a la base ni a otro servicio, y no se registra en las trazas.
"""
from __future__ import annotations

import json
import queue
import re
import threading
from collections import defaultdict
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path

import anyio
import jwt
from mcp.server.auth.middleware.auth_context import get_access_token
from mcp.server.auth.provider import AccessToken

from .primitivas import PLANTILLAS, Herramientas  # primitivas agrega semana-13 a sys.path

from herramientas import Contexto  # noqa: E402
from herramientas.herramientas import DICCIONARIO, TABLAS  # noqa: E402

PERMISOS = json.loads((Path(__file__).resolve().parents[1] / "auth" / "permisos_oauth.json").read_text(encoding="utf-8"))
SCOPE_BASE = PERMISOS["scope_base"]
SCOPES = ("legado:leer", "legado:ventas", "legado:proveedores", "legado:compras:proponer")
TABLA_SCOPE = {t: s for s, ts in PERMISOS["tablas_por_scope"].items() for t in ts}
_ESQUEMA = re.compile(r"^legado://esquema/([a-z0-9_]+)$")


# ---------- permisos por scope ----------

def scopes_de_tablas(tablas, columnas=()) -> set[str]:
    req = {TABLA_SCOPE[t] for t in tablas if t in TABLA_SCOPE}
    for c in columnas:
        req |= set(PERMISOS["columnas_restringidas"].get(c, []))
    return req


def scopes_requeridos(metodo: str | None, nombre: str | None) -> set[str]:
    """Scopes que pide una operación, calculados del cuerpo JSON-RPC (nunca del encabezado)."""
    req = {SCOPE_BASE}
    if metodo == "tools/call" and nombre in PERMISOS["herramientas"]:
        req |= set(PERMISOS["herramientas"][nombre])
    elif metodo == "resources/read" and nombre and (m := _ESQUEMA.match(nombre)):
        req |= scopes_de_tablas([m.group(1)])
    elif metodo == "prompts/get" and nombre in PLANTILLAS:
        p = PLANTILLAS[nombre]
        req |= scopes_de_tablas(p.tablas, p.columnas)
        for h in p.herramientas:
            req |= set(PERMISOS["herramientas"].get(h, []))
    return req


def rol_bd(scopes) -> str | None:
    clave = " ".join(sorted(set(scopes) & {"legado:leer", "legado:ventas", "legado:proveedores"}))
    return PERMISOS["roles_bd"].get(clave)


@dataclass
class ContextoOAuth(Contexto):
    """Contexto de la semana 13 cuyos permisos salen de los scopes del token."""
    scopes: frozenset = frozenset()
    cliente: str = ""

    @classmethod
    def de_token(cls, token: AccessToken, **kw) -> "ContextoOAuth":
        scopes = frozenset(token.scopes) & frozenset(SCOPES)
        roles = [r for s, r in PERMISOS["roles_internos"].items() if s in scopes]  # solo para proponer_orden_compra
        return cls(usuario=token.subject or token.client_id, roles=roles, scopes=scopes, cliente=token.client_id, **kw)

    def tablas(self) -> list[str]:
        if SCOPE_BASE not in self.scopes:
            return []
        visibles = {t for s in self.scopes for t in PERMISOS["tablas_por_scope"].get(s, [])}
        return [t for t in TABLAS if t in visibles]

    def columna_permitida(self, tabla: str, columna: str) -> bool:
        req = PERMISOS["columnas_restringidas"].get(f"{tabla}.{columna}")
        return req is None or bool(set(req) & self.scopes)

    def restringidas(self) -> set[str]:
        return {k.split(".")[1] for k, req in PERMISOS["columnas_restringidas"].items() if not set(req) & self.scopes}

    def herramienta_visible(self, nombre: str) -> bool:
        return set(PERMISOS["herramientas"].get(nombre, [SCOPE_BASE])) <= self.scopes


# ---------- validación del JWT ----------

class ErrorToken(Exception):
    pass


class VerificadorJWT:
    """TokenVerifier del SDK. `verificar` es síncrono (descarga el JWKS la primera vez); `verify_token` lo corre en un hilo."""

    def __init__(self, emisor: str, audiencia: str, jwks_uri: str, *, algoritmos=("RS256",), margen_s: int = 30,
                 cache_s: int = 300):
        self.emisor, self.audiencia, self.algoritmos, self.margen_s = emisor, audiencia, tuple(algoritmos), margen_s
        self.jwks = jwt.PyJWKClient(jwks_uri, cache_keys=True, lifespan=cache_s, timeout=10)

    def verificar(self, token: str) -> AccessToken:
        try:
            cabecera = jwt.get_unverified_header(token)
        except jwt.PyJWTError as e:
            raise ErrorToken(f"malformado: {e}") from None
        if cabecera.get("alg") not in self.algoritmos:          # rechaza none, HS256 y cualquier otro antes de nada
            raise ErrorToken(f"algoritmo no permitido: {cabecera.get('alg')!r}")
        try:
            clave = self.jwks.get_signing_key_from_jwt(token).key   # kid desconocido: refresca el JWKS una vez
            c = jwt.decode(token, clave, algorithms=list(self.algoritmos), audience=self.audiencia, issuer=self.emisor,
                           leeway=self.margen_s, options={"require": ["exp", "iat", "iss", "aud", "sub"]})
        except jwt.PyJWTError as e:
            raise ErrorToken(f"{type(e).__name__}: {e}") from None
        if c.get("typ", "Bearer") != "Bearer":                   # un ID token o un refresh token no son access tokens
            raise ErrorToken(f"tipo de token no permitido: {c.get('typ')!r}")
        return AccessToken(token=token, client_id=c.get("azp") or c.get("client_id") or "",
                           scopes=str(c.get("scope", "")).split(), expires_at=int(c["exp"]), resource=self.audiencia,
                           subject=c["sub"], claims={k: c[k] for k in ("iss", "azp", "sid") if k in c})

    async def verify_token(self, token: str) -> AccessToken | None:
        try:
            return await anyio.to_thread.run_sync(self.verificar, token)
        except ErrorToken:
            return None


@dataclass
class Rechazo:
    estado: int
    www_authenticate: str
    cuerpo: dict


class Autorizador:
    """Decide 401/403 para POST /mcp antes de que el SDK procese la petición."""

    def __init__(self, verificador: VerificadorJWT, url_metadatos: str):
        self.verificador, self.url_metadatos = verificador, url_metadatos

    def _desafio(self, scopes: set[str], error: str | None = None, descripcion: str | None = None) -> str:
        partes = []
        if error:
            partes.append(f'error="{error}"')
        if descripcion:
            partes.append(f'error_description="{descripcion}"')
        partes.append(f'scope="{" ".join(sorted(scopes))}"')
        partes.append(f'resource_metadata="{self.url_metadatos}"')
        return "Bearer " + ", ".join(partes)

    async def evaluar(self, encabezados: dict[bytes, bytes], metodo: str | None, nombre) -> tuple[AccessToken | None, Rechazo | None]:
        req = scopes_requeridos(metodo, nombre if isinstance(nombre, str) else None)
        auth = encabezados.get(b"authorization", b"").decode("latin-1")
        if not auth:
            return None, Rechazo(401, self._desafio(req), {"error": "invalid_token",
                                                            "error_description": "Authentication required"})
        esquema, _, token = auth.partition(" ")
        if esquema.lower() != "bearer" or not token.strip():
            return None, Rechazo(401, self._desafio(req, "invalid_request", "Bearer token required"),
                                 {"error": "invalid_request", "error_description": "Bearer token required"})
        try:
            at = await anyio.to_thread.run_sync(self.verificador.verificar, token.strip())
        except ErrorToken:
            # el motivo exacto no se devuelve al cliente (no se ayuda a fabricar tokens); queda como "invalid_token"
            return None, Rechazo(401, self._desafio(req, "invalid_token", "The access token is invalid or expired"),
                                 {"error": "invalid_token", "error_description": "The access token is invalid or expired"})
        faltan = req - set(at.scopes)
        if faltan:
            return at, Rechazo(403, self._desafio(req, "insufficient_scope", "Missing scope: " + " ".join(sorted(faltan))),
                               {"error": "insufficient_scope", "error_description": "Missing scope: " + " ".join(sorted(faltan)),
                                "scope": " ".join(sorted(req))})
        return at, None


# ---------- base de datos: pool y rol por perfil ----------

class PoolConexiones:
    """Conexiones propias por llamada (una conexión psycopg no se comparte entre transacciones concurrentes)."""

    def __init__(self, dsn: str, tamano: int = 4, espera_s: float = 10.0):
        self.dsn, self.tamano, self.espera_s = dsn, tamano, espera_s
        self._libres: queue.Queue = queue.Queue()
        self._creadas = 0
        self._lock = threading.Lock()

    def tomar(self):
        import psycopg
        try:
            return self._libres.get_nowait()
        except queue.Empty:
            pass
        with self._lock:
            if self._creadas < self.tamano:
                self._creadas += 1
                crear = True
            else:
                crear = False
        if crear:
            try:
                conn = psycopg.connect(self.dsn, autocommit=True)
                conn.execute("SET search_path = legado")
                return conn
            except Exception:
                with self._lock:
                    self._creadas -= 1
                raise
        return self._libres.get(timeout=self.espera_s)

    def devolver(self, conn):
        import psycopg
        if conn.closed or conn.info.transaction_status != psycopg.pq.TransactionStatus.IDLE:
            try:
                conn.close()
            finally:
                with self._lock:
                    self._creadas -= 1
            return
        self._libres.put(conn)

    def cerrar(self):
        while True:
            try:
                self._libres.get_nowait().close()
            except queue.Empty:
                return


class ConexionConRol:
    """Se comporta como la conexión que usa `Herramientas._correr` (transaction + execute), pero cada transacción toma una
    conexión del pool y empieza con SET LOCAL ROLE al rol del perfil. Sin rol (sin legado:leer) no hay acceso a la base."""

    def __init__(self, pool: PoolConexiones, rol: str | None):
        self.pool, self.rol = pool, rol
        self._local = threading.local()

    @contextmanager
    def transaction(self):
        from psycopg import sql
        from herramientas.herramientas import ErrorHerramienta
        if self.rol is None:
            raise ErrorHerramienta("permiso_denegado", "El token no da acceso a la base.", "Se requiere el scope legado:leer.")
        conn = self.pool.tomar()
        try:
            with conn.transaction():
                conn.execute(sql.SQL("SET LOCAL ROLE {}").format(sql.Identifier(self.rol)))
                self._local.conn = conn
                yield
        finally:
            self._local.conn = None
            self.pool.devolver(conn)

    def execute(self, *a, **k):
        return self._local.conn.execute(*a, **k)


def fabrica_oauth(pool: PoolConexiones | None, idioma: str = "es"):
    """Herramientas de la petición en curso, a partir del token que validó el middleware del SDK."""
    propuestas: dict[str, list] = defaultdict(list)   # por sujeto: las propuestas no se mezclan entre usuarios

    def fabrica() -> Herramientas:
        token = get_access_token()
        if token is None:   # no ocurre detrás de la frontera y del SDK; si ocurre, sin permisos
            token = AccessToken(token="", client_id="", scopes=[], subject="anonimo")
        rol = rol_bd(token.scopes) if SCOPE_BASE in token.scopes else None
        ctx = ContextoOAuth.de_token(token, conexion=ConexionConRol(pool, rol) if pool else None, idioma=idioma,
                                     propuestas=propuestas[token.subject or token.client_id])
        return Herramientas(ctx)
    return fabrica


def aplicar_roles_bd(admin_dsn: str) -> None:
    """Crea o actualiza los roles por perfil (idempotente). Requiere que exista copilot_nlq (herramientas/conexion.py)."""
    import psycopg
    with psycopg.connect(admin_dsn, autocommit=True) as conn:
        conn.execute((Path(__file__).resolve().parents[1] / "auth" / "roles_bd.sql").read_text(encoding="utf-8"))


def columnas_visibles(ctx: Contexto, tabla: str) -> list[str]:
    return [c for c in DICCIONARIO[tabla]["columnas"] if ctx.columna_permitida(tabla, c)]
