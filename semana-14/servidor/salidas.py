"""Contrato de salida de las 6 herramientas de la semana 13 (actividad 2 de la semana 14).

Cada herramienta devuelve `{"ok": true, ...}` o `{"ok": false, "error": {...}}` (contrato de la semana 13, sin cambios).
Aquí ese contrato se vuelve un `outputSchema` publicado en `tools/list`: unión (anyOf) del éxito propio de cada
herramienta y del error común, con `additionalProperties: false`, sin `$ref` (se resuelven en línea para que ningún
cliente tenga que seguir referencias) y raíz `type: object`.
"""
from __future__ import annotations

from typing import Any, Literal, Union

from pydantic import BaseModel, ConfigDict, TypeAdapter


class _Salida(BaseModel):
    model_config = ConfigDict(extra="forbid")


# ---------- error común ----------

class DetalleError(_Salida):
    tipo: str
    mensaje: str
    sugerencia: str


class Error(_Salida):
    ok: Literal[False]
    error: DetalleError


# ---------- describir_esquema ----------

class Columna(_Salida):
    columna: str
    descripcion: str


class Tabla(_Salida):
    tabla: str
    descripcion: str
    columnas: list[Columna]


class DescribirEsquemaOk(_Salida):
    ok: Literal[True]
    esquema: Literal["legado"]
    tablas: list[Tabla]
    nota: str


# ---------- buscar_regla_negocio ----------

class Regla(_Salida):
    id: str
    nombre: str
    definicion: str
    fuente: str


class BuscarReglaOk(_Salida):
    ok: Literal[True]
    reglas: list[Regla]
    sugerencia: str | None = None


# ---------- muestrear_valores ----------

class Valor(_Salida):
    valor: Any
    filas: int


class MuestrearValoresOk(_Salida):
    ok: Literal[True]
    tabla: str
    columna: str
    valores_distintos: int
    valores: list[Valor]


# ---------- validar_sql ----------

class ValidarSqlOk(_Salida):
    ok: Literal[True]
    valido: Literal[True]
    sql_normalizado: str


# ---------- ejecutar_sql ----------

class EjecutarSqlOk(_Salida):
    ok: Literal[True]
    columnas: list[str]
    total_filas: int
    filas_devueltas: int
    truncado: bool
    filas: list[list[Any]]
    sql_normalizado: str
    nota: str | None = None


# ---------- proponer_orden_compra ----------

class Propuesta(_Salida):
    id: str
    sku: str
    cantidad: int
    motivo: str
    estado: Literal["PENDING_APPROVAL"]  # nunca otra cosa: la herramienta solo registra
    ejecutada: Literal[False]


class ProponerOrdenCompraOk(_Salida):
    ok: Literal[True]
    propuesta: Propuesta
    nota: str


EXITOS: dict[str, type[_Salida]] = {
    "describir_esquema": DescribirEsquemaOk,
    "buscar_regla_negocio": BuscarReglaOk,
    "muestrear_valores": MuestrearValoresOk,
    "validar_sql": ValidarSqlOk,
    "ejecutar_sql": EjecutarSqlOk,
    "proponer_orden_compra": ProponerOrdenCompraOk,
}


def adaptador(nombre: str) -> TypeAdapter:
    return TypeAdapter(Union[EXITOS[nombre], Error])  # noqa: UP007


def _en_linea(nodo, defs):
    """Resuelve `{"$ref": "#/$defs/X"}` en línea (los modelos no son recursivos) y quita los `title`."""
    if isinstance(nodo, dict):
        if "$ref" in nodo:
            return _en_linea(defs[nodo["$ref"].rsplit("/", 1)[1]], defs)
        return {k: _en_linea(v, defs) for k, v in nodo.items() if k not in ("title", "$defs")}
    if isinstance(nodo, list):
        return [_en_linea(v, defs) for v in nodo]
    return nodo


def esquema_salida(nombre: str) -> dict:
    """outputSchema de la herramienta: {"type": "object", "anyOf": [éxito, error]} sin $ref."""
    crudo = adaptador(nombre).json_schema()
    esquema = _en_linea(crudo, crudo.get("$defs", {}))
    return {"type": "object", **esquema}


def validar(nombre: str, salida: dict):
    """Valida una salida real contra el contrato; levanta pydantic.ValidationError si no cumple."""
    return adaptador(nombre).validate_python(salida)
