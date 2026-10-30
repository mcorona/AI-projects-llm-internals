"""Conexión de solo lectura para las herramientas de semana 13.

Orden de preferencia:
1. NLQ_LEGADO_DSN: rol copilot_nlq ya creado (solo SELECT sobre las vistas legado, read-only por defecto).
2. PG_ADMIN_DSN: (re)crea copilot_nlq con una clave aleatoria de la sesión, como la NLQ endurecida de semana 10, y se
   conecta con él. La clave no se guarda en ningún lado.
3. PG_DSN: rol copilot_ro, con search_path = legado. El guard y la transacción READ ONLY siguen aplicando.
"""
import os
import secrets

import psycopg
from psycopg import sql as pgsql
from psycopg.conninfo import make_conninfo


def crear_rol_nlq() -> str:
    clave = secrets.token_urlsafe(24)
    with psycopg.connect(os.environ["PG_ADMIN_DSN"], autocommit=True) as conn:
        if not conn.execute("SELECT 1 FROM pg_roles WHERE rolname = 'copilot_nlq'").fetchone():
            conn.execute("CREATE ROLE copilot_nlq LOGIN")
        conn.execute(pgsql.SQL("ALTER ROLE copilot_nlq WITH LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT "
                               "PASSWORD {}").format(pgsql.Literal(clave)))
        conn.execute("ALTER ROLE copilot_nlq SET default_transaction_read_only = on")
        conn.execute("ALTER ROLE copilot_nlq SET search_path = legado")
        conn.execute("GRANT USAGE ON SCHEMA legado TO copilot_nlq")
        conn.execute("GRANT SELECT ON ALL TABLES IN SCHEMA legado TO copilot_nlq")
    return make_conninfo(os.environ.get("PG_DSN") or os.environ["PG_ADMIN_DSN"], user="copilot_nlq", password=clave)


def conectar() -> tuple[psycopg.Connection, str]:
    """Devuelve (conexión en autocommit, nombre del rol)."""
    if os.environ.get("NLQ_LEGADO_DSN"):
        dsn = os.environ["NLQ_LEGADO_DSN"]
    elif os.environ.get("PG_ADMIN_DSN"):
        dsn = crear_rol_nlq()
        # Las siguientes conexiones del proceso (hilos, servidor MCP hijo) reusan esta clave en lugar de rotarla.
        os.environ["NLQ_LEGADO_DSN"] = dsn
    else:
        dsn = os.environ["PG_DSN"]
    conn = psycopg.connect(dsn, autocommit=True)
    conn.execute("SET search_path = legado")
    rol = conn.execute("SELECT current_user").fetchone()[0]
    return conn, rol
