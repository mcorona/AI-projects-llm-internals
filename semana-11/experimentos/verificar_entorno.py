"""Semana 11, pendiente previo: verifica LM Studio (bge-m3) y el índice semana10.chunks en copilot-db.

- LM Studio: el modelo de embeddings responde y su dimensión coincide con la del índice.
- copilot-db: semana10.chunks existe, cuántos chunks hay por tenant y documento, y si trae documentos que no son
  del índice de la actividad 7 (beta de semana 9 o inyectados de la actividad 8, que agrega seguridad.py).
Si el índice no es el de la actividad 7 (30 documentos, 68 chunks, solo tenant alfa), reindexa con
`python -c "import sys; sys.path.insert(0, 'semana-10/experimentos'); import asistente; asistente.indexar()"`.
Requiere PG_ADMIN_DSN.
"""
import json
import os
import urllib.request

import psycopg

base = os.getenv("LMSTUDIO_BASE_URL", "http://localhost:1234/v1")
modelo = os.getenv("LMSTUDIO_EMBED_MODEL", "text-embedding-bge-m3")
req = urllib.request.Request(f"{base}/embeddings", data=json.dumps({"model": modelo, "input": ["prueba"]}).encode(),
                             headers={"Content-Type": "application/json"})
with urllib.request.urlopen(req, timeout=60) as r:
    dim = len(json.loads(r.read())["data"][0]["embedding"])
print(f"LM Studio: {modelo} responde, dimensión {dim}")

with psycopg.connect(os.environ["PG_ADMIN_DSN"]) as conn:
    if not conn.execute("SELECT to_regclass('semana10.chunks')").fetchone()[0]:
        raise SystemExit("semana10.chunks no existe: reindexa con asistente.indexar() (ver docstring)")
    dim_idx = conn.execute("SELECT vector_dims(embedding) FROM semana10.chunks LIMIT 1").fetchone()[0]
    por_tenant = conn.execute("SELECT tenant_id, count(DISTINCT source), count(*) FROM semana10.chunks GROUP BY 1 ORDER BY 1").fetchall()
    extra = [s for (s,) in conn.execute("SELECT DISTINCT source FROM semana10.chunks WHERE source LIKE '%inyeccion%' ORDER BY 1")]
print(f"semana10.chunks: dimensión {dim_idx}; por tenant (documentos, chunks): {por_tenant}")
print(f"documentos con instrucción inyectada: {extra or 'ninguno'}")
limpio = por_tenant == [("alfa", 30, 68)] and dim_idx == dim
print("ÍNDICE OK (actividad 7: 30 documentos, 68 chunks, solo alfa)" if limpio else
      "ÍNDICE NO COINCIDE con el de la actividad 7: reindexar (ver docstring)")
