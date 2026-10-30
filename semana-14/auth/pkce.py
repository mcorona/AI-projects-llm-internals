"""Cliente OAuth 2.1 mínimo para el laboratorio: authorization code + PKCE (S256) + resource (RFC 8707) contra Keycloak.

Hace lo que haría un navegador sin abrir uno: pide /auth, llena el formulario de login con el usuario de prueba,
captura el redirect a loopback (sin seguirlo), valida `state` e `iss` (RFC 9207) y canjea el código con el
`code_verifier`. Solo usa la biblioteca estándar. Es para pruebas y para el agente del laboratorio (actividad 7);
un cliente real usaría el navegador del usuario y un listener en 127.0.0.1.

    from auth.pkce import obtener_token, claims
    tok = obtener_token("analista", password, ["legado:leer"])
    claims(tok["access_token"])["aud"]   # -> "http://127.0.0.1:8014/mcp"
"""
from __future__ import annotations

import base64
import hashlib
import html
import http.cookiejar
import json
import os
import re
import secrets
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

KC_URL = os.environ.get("KEYCLOAK_URL", "http://127.0.0.1:8180")
REALM = "legacybridge"
EMISOR = f"{KC_URL}/realms/{REALM}"
CLIENTE = "legacybridge-agente"
RECURSO = "http://127.0.0.1:8014/mcp"
REDIRECT = "http://127.0.0.1:53682/callback"
SECRETOS = Path(__file__).resolve().parent / ".secretos.env"
SCOPES_TODOS = ("legado:leer", "legado:ventas", "legado:proveedores", "legado:compras:proponer")


class ErrorOAuth(Exception):
    def __init__(self, error: str, descripcion: str = "", etapa: str = ""):
        super().__init__(f"{etapa}: {error} {descripcion}".strip())
        self.error, self.descripcion, self.etapa = error, descripcion, etapa


class _LoopbackSeguro(http.cookiejar.DefaultCookiePolicy):
    """Como un navegador: http://127.0.0.1 y http://localhost son contexto seguro, así que reciben las cookies `Secure`
    de Keycloak. Cualquier otro host por http no las recibe (comportamiento por defecto)."""

    def return_ok_secure(self, cookie, request):
        host = urllib.parse.urlsplit(request.get_full_url()).hostname
        return host in ("127.0.0.1", "localhost", "::1") or super().return_ok_secure(cookie, request)


class _SinRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **k):
        return None   # el 302 llega como HTTPError y se lee su Location


def secretos() -> dict:
    """Contraseñas locales que generó arrancar.sh (nunca en Git)."""
    out = {}
    for linea in SECRETOS.read_text(encoding="utf-8").splitlines():
        if "=" in linea and not linea.startswith("#"):
            k, v = linea.split("=", 1)
            out[k.strip()] = v.strip()
    return out


def password(usuario: str) -> str:
    return secretos()[f"KC_PWD_{usuario.upper()}"]


def descubrimiento(emisor: str = EMISOR) -> dict:
    with urllib.request.urlopen(f"{emisor}/.well-known/openid-configuration", timeout=10) as r:
        return json.load(r)


def pkce_par(metodo: str = "S256") -> tuple[str, str]:
    verifier = base64.urlsafe_b64encode(secrets.token_bytes(48)).rstrip(b"=").decode()
    if metodo == "plain":
        return verifier, verifier
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    return verifier, challenge


def claims(jwt: str) -> dict:
    """Payload del JWT SIN verificar la firma (solo para inspeccionar en pruebas; el servidor sí verifica)."""
    cuerpo = jwt.split(".")[1]
    return json.loads(base64.urlsafe_b64decode(cuerpo + "=" * (-len(cuerpo) % 4)))


def autorizar(usuario: str, clave: str, scopes, *, resource: str | None = RECURSO, redirect: str = REDIRECT,
              cliente: str = CLIENTE, metodo: str | None = "S256", emisor: str = EMISOR) -> dict:
    """Paso de autorización: devuelve {code, state, iss, verifier, redirect, resource} o lanza ErrorOAuth."""
    meta = descubrimiento(emisor)
    jar = http.cookiejar.CookieJar(policy=_LoopbackSeguro())
    abrir = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar), _SinRedirect()).open
    verifier, challenge = pkce_par(metodo or "S256")
    state = secrets.token_urlsafe(16)
    params = {"response_type": "code", "client_id": cliente, "redirect_uri": redirect, "scope": " ".join(scopes),
              "state": state}
    if metodo:
        params |= {"code_challenge": challenge, "code_challenge_method": metodo}
    if resource:
        params["resource"] = resource

    def _seguir(url, datos=None):
        try:
            r = abrir(url, data=urllib.parse.urlencode(datos).encode() if datos else None, timeout=15)
            return r.status, r.read().decode("utf-8", "replace"), None
        except urllib.error.HTTPError as e:
            return e.code, e.read().decode("utf-8", "replace"), e.headers.get("Location")

    estado, pagina, ubicacion = _seguir(meta["authorization_endpoint"] + "?" + urllib.parse.urlencode(params))
    if ubicacion is None:
        m = re.search(r'<form[^>]+id="kc-form-login"[^>]+action="([^"]+)"', pagina)
        if not m:
            msg = re.search(r'(?s)class="[^"]*(?:instruction|kc-feedback-text|alert)[^"]*"[^>]*>(.*?)<', pagina)
            raise ErrorOAuth("pagina_de_error", html.unescape(msg.group(1)).strip() if msg else f"HTTP {estado}",
                             "autorizacion")
        estado, pagina, ubicacion = _seguir(html.unescape(m.group(1)),
                                            {"username": usuario, "password": clave, "credentialId": ""})
    if not ubicacion:
        raise ErrorOAuth("login_fallido", f"HTTP {estado}", "login")
    if not ubicacion.startswith(redirect.split("?")[0]):
        raise ErrorOAuth("redirect_inesperado", ubicacion, "autorizacion")
    q = dict(urllib.parse.parse_qsl(urllib.parse.urlsplit(ubicacion).query))
    # RFC 9207: comparar iss con el emisor registrado antes de usar el código o el error
    if meta.get("authorization_response_iss_parameter_supported") and q.get("iss") != meta["issuer"]:
        raise ErrorOAuth("iss_invalido", f"{q.get('iss')!r} != {meta['issuer']!r}", "autorizacion")
    if q.get("state") != state:
        raise ErrorOAuth("state_invalido", "", "autorizacion")
    if "error" in q:
        raise ErrorOAuth(q["error"], q.get("error_description", ""), "autorizacion")
    return {"code": q["code"], "state": state, "iss": q.get("iss"), "verifier": verifier, "redirect": redirect,
            "resource": resource, "token_endpoint": meta["token_endpoint"], "cliente": cliente}


def canjear(aut: dict, *, verifier: str | None = None, resource: str | None = ...) -> dict:
    datos = {"grant_type": "authorization_code", "code": aut["code"], "redirect_uri": aut["redirect"],
             "client_id": aut["cliente"], "code_verifier": verifier or aut["verifier"]}
    res = aut["resource"] if resource is ... else resource
    if res:
        datos["resource"] = res
    return _token(aut["token_endpoint"], datos)


def _token(endpoint: str, datos: dict) -> dict:
    try:
        with urllib.request.urlopen(endpoint, data=urllib.parse.urlencode(datos).encode(), timeout=15) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        cuerpo = json.loads(e.read() or b"{}")
        raise ErrorOAuth(cuerpo.get("error", str(e.code)), cuerpo.get("error_description", ""), "token") from None


def refrescar(token: dict, *, resource: str | None = RECURSO, cliente: str = CLIENTE, emisor: str = EMISOR) -> dict:
    datos = {"grant_type": "refresh_token", "refresh_token": token["refresh_token"], "client_id": cliente}
    if resource:
        datos["resource"] = resource
    return _token(descubrimiento(emisor)["token_endpoint"], datos)


def obtener_token(usuario: str, clave: str | None = None, scopes=SCOPES_TODOS, **kw) -> dict:
    """Flujo completo: autorizar + canjear. Devuelve la respuesta del token endpoint (access_token, refresh_token...)."""
    return canjear(autorizar(usuario, clave or password(usuario), scopes, **kw))
