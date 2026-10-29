"""Semana 13, actividad 1: golden set de tareas del agente (ES/EN) sobre el flujo de LegacyBridge.

Cada tarea pide un resultado de negocio sobre el esquema legado de semana 10. El resultado esperado se obtiene
ejecutando el SQL de referencia (sobre las tablas originales de inventory-copilot, como el set difícil de semana 7)
con el rol de solo lectura. Las vistas `legado` exponen los mismos datos con nombres crípticos, así que el agente,
que solo ve `legado`, debe llegar al mismo resultado.

Tipos (por idioma): 10 simples (set difícil de semana 7), 12 con reglas de negocio, 8 compuestas, 4 con trampas de
valores, 4 ambiguas (se espera aclaración) y 4 sin respuesta en los datos (se espera abstención).

Salida de cada tarea: un diccionario de claves; cada clave es un resultado (filas, conjunto, número o texto) que el
agente reporta con el SQL que lo produce y su valor. La evaluación vuelve a ejecutar ese SQL y lo compara con el de
referencia con el comparador de semana 7 (`results_match`).

Uso:
    PG_DSN=... python3 construir_tareas.py            # valida contra la BD y escribe tareas_{es,en}.jsonl y manifiesto.json
    python3 construir_tareas.py --solo-listar         # imprime las tareas sin conectarse
"""
import argparse
import hashlib
import importlib.util
import json
import os
import sys
from pathlib import Path

AQUI = Path(__file__).resolve().parent
RAIZ = AQUI.parents[1]

BASE = """WITH corte AS (SELECT MAX(day) AS d FROM sales_daily),
tot AS (SELECT p.sku, COALESCE(SUM(s.on_hand), 0) AS total FROM products p LEFT JOIN stock s ON s.sku = p.sku GROUP BY p.sku),
v30 AS (SELECT p.sku, COALESCE(SUM(d.units), 0) / 30.0 AS vdp FROM products p
        LEFT JOIN sales_daily d ON d.sku = p.sku AND d.day > (SELECT d FROM corte) - 30 GROUP BY p.sku),
v90 AS (SELECT p.sku, COALESCE(SUM(d.units), 0) / 90.0 AS vdp FROM products p
        LEFT JOIN sales_daily d ON d.sku = p.sku AND d.day > (SELECT d FROM corte) - 90 GROUP BY p.sku),
cob AS (SELECT t.sku, t.total, v.vdp, CASE WHEN v.vdp > 0 THEN t.total / v.vdp END AS dias FROM tot t JOIN v30 v USING (sku)),
riesgo AS (SELECT p.sku FROM cob c JOIN products p USING (sku) JOIN suppliers s ON s.supplier_id = p.supplier_id
           WHERE p.critical AND c.dias < s.lead_time_days),
exced AS (SELECT st.sku, st.warehouse_id FROM stock st JOIN tot t USING (sku) WHERE t.total > 0 AND st.on_hand > 1.5 * t.total / 3.0),
abiertas AS (SELECT o.*, o.qty * p.unit_cost AS monto, p.critical FROM purchase_orders o JOIN products p USING (sku)
             WHERE o.status IN ('PENDING_APPROVAL', 'APPROVED')),
clase_a AS (SELECT sku FROM (SELECT p.sku, p.critical, ROW_NUMBER() OVER (ORDER BY t.total * p.unit_cost DESC, p.sku) AS rn
            FROM tot t JOIN products p USING (sku)) x WHERE critical OR rn <= CEIL(0.2 * (SELECT COUNT(*) FROM products))),
prop AS (SELECT t.sku, p.critical, CEIL(v.vdp * CASE WHEN p.critical THEN 45 ELSE 30 END) AS qty,
         CEIL(v.vdp * CASE WHEN p.critical THEN 45 ELSE 30 END) * p.unit_cost AS monto
         FROM tot t JOIN products p USING (sku) JOIN v90 v USING (sku)
         WHERE t.total < p.reorder_point AND t.sku NOT IN (SELECT sku FROM abiertas))
"""


def k(tipo, es, en, sql, orden=False):
    """Una clave de salida: tipo (filas | conjunto | numero | texto), descripción ES/EN, SQL de referencia."""
    return {"tipo": tipo, "es": es, "en": en, "sql": sql, "orden": orden}


SIMPLES = ["hard-001", "hard-002", "hard-006", "hard-011", "hard-020", "hard-021", "hard-026", "hard-035", "hard-038", "hard-040"]

REGLAS = [
    ("r01", "¿Cuántos SKU críticos están en nivel 2 de escalamiento?", "How many critical SKUs are at escalation level 2?",
     ["R-ESCALA", "R-COB", "R-CORTE", "R-STOCK"],
     {"n": k("numero", "número de SKU", "number of SKUs",
             BASE + "SELECT COUNT(*) FROM cob c JOIN products p USING (sku) WHERE p.critical AND c.dias < 7")}),
    ("r02", "¿Qué SKU críticos están en riesgo?", "Which critical SKUs are at risk?",
     ["R-RIESGO", "R-COB", "R-CORTE", "R-STOCK"],
     {"skus": k("conjunto", "códigos de SKU", "SKU codes", BASE + "SELECT sku FROM riesgo")}),
    ("r03", "¿Cuántos SKU críticos están en nivel 1 de escalamiento?", "How many critical SKUs are at escalation level 1?",
     ["R-ESCALA", "R-REORDEN", "R-RIESGO", "R-COB", "R-CORTE", "R-STOCK"],
     {"n": k("numero", "número de SKU", "number of SKUs",
             BASE + "SELECT COUNT(*) FROM tot t JOIN products p USING (sku) WHERE p.critical AND (t.total < p.reorder_point OR t.sku IN (SELECT sku FROM riesgo))")}),
    ("r04", "¿Cuántos SKU están por debajo de su punto de reorden según la política de reorden?",
     "How many SKUs are below their reorder point according to the reorder policy?",
     ["R-REORDEN", "R-STOCK"],
     {"n": k("numero", "número de SKU", "number of SKUs",
             BASE + "SELECT COUNT(*) FROM tot t JOIN products p USING (sku) WHERE t.total < p.reorder_point")}),
    ("r05", "¿Qué SKU críticos deben tener un proveedor alterno homologado?",
     "Which critical SKUs must have an approved alternate supplier?",
     ["R-ALTERNO"],
     {"skus": k("conjunto", "códigos de SKU", "SKU codes",
                "SELECT p.sku FROM products p JOIN suppliers s ON s.supplier_id = p.supplier_id WHERE p.critical AND s.lead_time_days > 20")}),
    ("r06", "¿Cuál es el monto total, en MXN, de las propuestas de orden de compra que se generan en la fecha de corte? Redondea a 2 decimales.",
     "What is the total amount, in MXN, of the purchase order proposals generated on the cutoff date? Round to 2 decimals.",
     ["R-PROPUESTA", "R-REORDEN", "R-STOCK", "R-OC-ABIERTA", "R-CORTE"],
     {"monto": k("numero", "monto total en MXN", "total amount in MXN", BASE + "SELECT ROUND(SUM(monto), 2) FROM prop")}),
    ("r07", "¿Cuántas de las propuestas de orden de compra de la fecha de corte debe aprobar el gerente de compras?",
     "How many of the purchase order proposals on the cutoff date must be approved by the purchasing manager?",
     ["R-PROPUESTA", "R-OC-APRUEBA", "R-REORDEN", "R-STOCK", "R-OC-ABIERTA", "R-CORTE"],
     {"n": k("numero", "número de propuestas", "number of proposals", BASE + "SELECT COUNT(*) FROM prop WHERE monto BETWEEN 50000 AND 250000")}),
    ("r08", "¿Cuántas de las propuestas de orden de compra de la fecha de corte requieren tres cotizaciones?",
     "How many of the purchase order proposals on the cutoff date require three quotes?",
     ["R-PROPUESTA", "R-OC-COTIZA", "R-REORDEN", "R-STOCK", "R-OC-ABIERTA", "R-CORTE"],
     {"n": k("numero", "número de propuestas", "number of proposals", BASE + "SELECT COUNT(*) FROM prop WHERE monto > 100000")}),
    ("r09", "¿Qué CEDIS tiene excedente en más SKU? Desempata por nombre del CEDIS en orden ascendente.",
     "Which distribution center has a surplus in the most SKUs? Break ties by distribution center name in ascending order.",
     ["R-EXCEDENTE", "R-STOCK"],
     {"cedis": k("texto", "nombre del CEDIS", "distribution center name",
                 BASE + "SELECT w.name FROM exced e JOIN warehouses w USING (warehouse_id) GROUP BY w.name ORDER BY COUNT(*) DESC, w.name LIMIT 1")}),
    ("r10", "¿Cuántos SKU son clase A en el inventario cíclico?", "How many SKUs are class A for cycle counting?",
     ["R-ABC", "R-STOCK"],
     {"n": k("numero", "número de SKU", "number of SKUs", BASE + "SELECT COUNT(*) FROM clase_a")}),
    ("r11", "¿Cuántos SKU tienen un punto de reorden registrado menor que el que resulta de la política de reorden?",
     "How many SKUs have a recorded reorder point lower than the one that results from the reorder policy?",
     ["R-PTR-POLITICA", "R-CORTE"],
     {"n": k("numero", "número de SKU", "number of SKUs",
             BASE + "SELECT COUNT(*) FROM products p JOIN suppliers s ON s.supplier_id = p.supplier_id JOIN v90 USING (sku) "
                    "WHERE p.reorder_point < v90.vdp * s.lead_time_days * CASE WHEN p.critical THEN 1.5 ELSE 1.2 END")}),
    ("r12", "¿Cuál es el monto total, en MXN, de las órdenes abiertas de SKU críticos? Redondea a 2 decimales.",
     "What is the total amount, in MXN, of open orders for critical SKUs? Round to 2 decimals.",
     ["R-OC-ABIERTA", "R-OC-MONTO"],
     {"monto": k("numero", "monto total en MXN", "total amount in MXN",
                 BASE + "SELECT ROUND(COALESCE(SUM(monto), 0), 2) FROM abiertas WHERE critical")}),
]

COMPUESTAS = [
    ("c01", "¿Qué SKU críticos están en riesgo y cuáles de ellos tienen excedente en algún CEDIS para transferir antes de comprar?",
     "Which critical SKUs are at risk, and which of them have a surplus in some distribution center to transfer before buying?",
     ["R-RIESGO", "R-COB", "R-CORTE", "R-STOCK", "R-EXCEDENTE"],
     {"en_riesgo": k("conjunto", "SKU críticos en riesgo", "critical SKUs at risk", BASE + "SELECT sku FROM riesgo"),
      "con_excedente": k("conjunto", "SKU en riesgo con excedente en algún CEDIS", "at-risk SKUs with a surplus in some distribution center",
                         BASE + "SELECT DISTINCT r.sku FROM riesgo r JOIN exced e USING (sku)")}),
    ("c02", "De las propuestas de orden de compra de la fecha de corte, ¿cuántas aprueba el comprador, cuántas el gerente de compras y cuántas el director de operaciones?",
     "Of the purchase order proposals on the cutoff date, how many are approved by the buyer, how many by the purchasing manager and how many by the operations director?",
     ["R-PROPUESTA", "R-OC-APRUEBA", "R-REORDEN", "R-STOCK", "R-OC-ABIERTA", "R-CORTE"],
     {f"{q}": k("numero", f"propuestas que aprueba: {d_es}", f"proposals approved by: {d_en}", BASE + "SELECT COUNT(*) FROM prop WHERE " + c)
      for q, d_es, d_en, c in [("comprador", "comprador", "buyer", "monto < 50000"),
                               ("gerente", "gerente de compras", "purchasing manager", "monto BETWEEN 50000 AND 250000"),
                               ("director", "director de operaciones", "operations director", "monto > 250000")]}),
    ("c03", "¿Qué SKU están por debajo de su punto de reorden y no tienen una orden abierta, y cuántos de ellos son críticos?",
     "Which SKUs are below their reorder point and have no open order, and how many of them are critical?",
     ["R-REORDEN", "R-STOCK", "R-OC-ABIERTA"],
     {"skus": k("conjunto", "SKU candidatos a nueva propuesta", "SKUs that are candidates for a new proposal",
                BASE + "SELECT t.sku FROM tot t JOIN products p USING (sku) WHERE t.total < p.reorder_point AND t.sku NOT IN (SELECT sku FROM abiertas)"),
      "criticos": k("numero", "cuántos de ellos son críticos", "how many of them are critical",
                    BASE + "SELECT COUNT(*) FROM tot t JOIN products p USING (sku) WHERE t.total < p.reorder_point AND p.critical AND t.sku NOT IN (SELECT sku FROM abiertas)")}),
    ("c04", "¿Qué proveedor tiene más SKU críticos en riesgo y cuál es su tiempo de entrega pactado? Desempata por nombre del proveedor en orden ascendente.",
     "Which supplier has the most critical SKUs at risk, and what is its agreed lead time? Break ties by supplier name in ascending order.",
     ["R-RIESGO", "R-COB", "R-CORTE", "R-STOCK"],
     {"proveedor": k("texto", "nombre del proveedor", "supplier name",
                     BASE + "SELECT s.name FROM riesgo r JOIN products p USING (sku) JOIN suppliers s ON s.supplier_id = p.supplier_id GROUP BY s.name ORDER BY COUNT(*) DESC, s.name LIMIT 1"),
      "dias": k("numero", "tiempo de entrega en días", "lead time in days",
                BASE + "SELECT s.lead_time_days FROM riesgo r JOIN products p USING (sku) JOIN suppliers s ON s.supplier_id = p.supplier_id GROUP BY s.name, s.lead_time_days ORDER BY COUNT(*) DESC, s.name LIMIT 1")}),
    ("c05", "¿En cuántos SKU tiene excedente cada CEDIS (Ciudad de México, Guadalajara y Monterrey)?",
     "In how many SKUs does each distribution center (Mexico City, Guadalajara and Monterrey) have a surplus?",
     ["R-EXCEDENTE", "R-STOCK"],
     {c: k("numero", f"SKU con excedente en {n}", f"SKUs with a surplus in {n}",
           BASE + f"SELECT COUNT(*) FROM exced e JOIN warehouses w USING (warehouse_id) WHERE w.city = '{n}'")
      for c, n in [("cdmx", "Ciudad de Mexico"), ("guadalajara", "Guadalajara"), ("monterrey", "Monterrey")]}),
    ("c06", "¿Cuál es la cobertura promedio, en días, de los SKU críticos con ventas en los últimos 30 días, y cuántos SKU críticos tienen menos de 7 días? Redondea la cobertura a 1 decimal.",
     "What is the average coverage, in days, of critical SKUs with sales in the last 30 days, and how many critical SKUs have fewer than 7 days? Round coverage to 1 decimal.",
     ["R-COB", "R-CORTE", "R-STOCK"],
     {"cobertura": k("numero", "cobertura promedio en días", "average coverage in days",
                     BASE + "SELECT ROUND(AVG(c.dias), 1) FROM cob c JOIN products p USING (sku) WHERE p.critical AND c.dias IS NOT NULL"),
      "menos_7": k("numero", "SKU críticos con menos de 7 días", "critical SKUs with fewer than 7 days",
                   BASE + "SELECT COUNT(*) FROM cob c JOIN products p USING (sku) WHERE p.critical AND c.dias < 7")}),
    ("c07", "¿Cuál es el valor total del inventario a costo, en MXN, y qué porcentaje de ese valor concentran los SKU clase A? Redondea el valor a 2 decimales y el porcentaje a 1 decimal.",
     "What is the total inventory value at cost, in MXN, and what percentage of that value do class A SKUs hold? Round the value to 2 decimals and the percentage to 1 decimal.",
     ["R-ABC", "R-STOCK"],
     {"valor": k("numero", "valor total en MXN", "total value in MXN",
                 BASE + "SELECT ROUND(SUM(t.total * p.unit_cost), 2) FROM tot t JOIN products p USING (sku)"),
      "pct_clase_a": k("numero", "porcentaje del valor en clase A", "percentage of value in class A",
                       BASE + "SELECT ROUND(100 * SUM(t.total * p.unit_cost) FILTER (WHERE t.sku IN (SELECT sku FROM clase_a)) / SUM(t.total * p.unit_cost), 1) FROM tot t JOIN products p USING (sku)")}),
    ("c08", "¿Qué SKU críticos surtidos por proveedores de China están en riesgo, y cuántas unidades vendieron en total en los últimos 30 días?",
     "Which critical SKUs supplied by Chinese suppliers are at risk, and how many units did they sell in total over the last 30 days?",
     ["R-RIESGO", "R-COB", "R-CORTE", "R-STOCK"],
     {"skus": k("conjunto", "códigos de SKU", "SKU codes",
                BASE + "SELECT r.sku FROM riesgo r JOIN products p USING (sku) JOIN suppliers s ON s.supplier_id = p.supplier_id WHERE s.country = 'CN'"),
      "unidades": k("numero", "unidades vendidas en 30 días", "units sold over 30 days",
                    BASE + "SELECT COALESCE(SUM(d.units), 0) FROM sales_daily d WHERE d.day > (SELECT d FROM corte) - 30 AND d.sku IN "
                           "(SELECT r.sku FROM riesgo r JOIN products p USING (sku) JOIN suppliers s ON s.supplier_id = p.supplier_id WHERE s.country = 'CN')")}),
]

VALORES = [
    ("v01", "¿Cuántos productos de la línea Tornillería son surtidos por proveedores de Estados Unidos?",
     "How many Tornillería line products are supplied by United States suppliers?",
     {"n": k("numero", "número de productos", "number of products",
             "SELECT COUNT(*) FROM products p JOIN suppliers s ON s.supplier_id = p.supplier_id WHERE p.category = 'Tornilleria' AND s.country = 'US'")}),
    ("v02", "¿Cuántas unidades en existencia hay en total en el CEDIS de Guadalajara?",
     "How many units are on hand in total at the Guadalajara distribution center?",
     {"unidades": k("numero", "unidades en existencia", "units on hand",
                    "SELECT COALESCE(SUM(s.on_hand), 0) FROM stock s JOIN warehouses w USING (warehouse_id) WHERE w.city = 'Guadalajara'")}),
    ("v03", "¿Qué proveedores alemanes tienen un tiempo de entrega mayor a 25 días?",
     "Which German suppliers have a lead time greater than 25 days?",
     {"proveedores": k("conjunto", "nombres de proveedor", "supplier names",
                       "SELECT name FROM suppliers WHERE country = 'DE' AND lead_time_days > 25")}),
    ("v04", "¿Cuántas unidades en existencia tienen en total los productos de la línea Hidráulica en el CEDIS de Monterrey?",
     "How many units on hand do Hidráulica line products have in total at the Monterrey distribution center?",
     {"unidades": k("numero", "unidades en existencia", "units on hand",
                    "SELECT COALESCE(SUM(s.on_hand), 0) FROM stock s JOIN products p USING (sku) JOIN warehouses w USING (warehouse_id) WHERE p.category = 'Hidraulico' AND w.city = 'Monterrey'")}),
]

AMBIGUAS = [
    ("a01", "¿Cuál es el mejor proveedor?", "Who is the best supplier?",
     "No hay criterio: tiempo de entrega, costo, número de SKU o los indicadores OTIF y de calidad, que no están en los datos."),
    ("a02", "¿Cuántas unidades vendió el SKU?", "How many units did the SKU sell?",
     "No dice qué SKU ni en qué periodo."),
    ("a03", "Dame los productos con poco inventario.", "Give me the products with low inventory.",
     "\"Poco\" puede ser por debajo del punto de reorden, en riesgo por cobertura o con existencia en cero, y no dice si en total o por CEDIS."),
    ("a04", "¿Cuánto inventario tenemos en el CEDIS?", "How much inventory do we have at the distribution center?",
     "No dice cuál de los tres CEDIS, ni si en unidades o en valor."),
]

SIN_RESPUESTA = [
    ("n01", "¿Cuál es el margen de utilidad de cada SKU?", "What is the profit margin of each SKU?",
     "Solo hay costo unitario; no hay precio de venta."),
    ("n02", "¿Qué cliente compró más unidades en septiembre de 2026?", "Which customer bought the most units in September 2026?",
     "Las ventas diarias no registran clientes."),
    ("n03", "¿Cuál fue el OTIF de cada proveedor el último trimestre?", "What was each supplier's OTIF last quarter?",
     "Los datos no registran entregas a tiempo ni completas."),
    ("n04", "¿Cuántas unidades están en tránsito entre CEDIS?", "How many units are in transit between distribution centers?",
     "No hay datos de transferencias."),
]

PASOS_MIN = {"simple": 2, "regla": 3, "compuesta": 4, "valores": 3, "ambigua": 1, "sin_respuesta": 1}
HERRAMIENTAS = {"simple": ["describir_esquema", "ejecutar_sql"],
                "regla": ["buscar_regla_negocio", "describir_esquema", "ejecutar_sql"],
                "compuesta": ["buscar_regla_negocio", "describir_esquema", "ejecutar_sql"],
                "valores": ["describir_esquema", "muestrear_valores", "ejecutar_sql"],
                "ambigua": [], "sin_respuesta": ["describir_esquema"]}


def cargar_comparador():
    spec = importlib.util.spec_from_file_location("run_eval7", RAIZ / "semana-07" / "run_eval.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def tareas_base():
    """Lista de tareas con texto en ambos idiomas y SQL de referencia por clave."""
    hard = {}
    for linea in open(RAIZ / "semana-07" / "datasets" / "nlq_hard_validado.jsonl", encoding="utf-8"):
        d = json.loads(linea)
        hard.setdefault(d["id"].rsplit("-", 1)[0], {})[d["lang"]] = d
    t = []
    for i, h in enumerate(SIMPLES, 1):
        es, en = hard[h]["es"], hard[h]["en"]
        t.append({"id": f"s{i:02d}", "tipo": "simple", "origen": h, "es": es["question"], "en": en["question"], "reglas": [],
                  "salida": {"filas": k("filas", "filas del resultado", "result rows", es["sql"], es.get("order_matters", False))},
                  "estado": "respondida"})
    for tid, es, en, reglas, salida in REGLAS:
        t.append({"id": tid, "tipo": "regla", "es": es, "en": en, "reglas": reglas, "salida": salida, "estado": "respondida"})
    for tid, es, en, reglas, salida in COMPUESTAS:
        t.append({"id": tid, "tipo": "compuesta", "es": es, "en": en, "reglas": reglas, "salida": salida, "estado": "respondida"})
    for tid, es, en, salida in VALORES:
        t.append({"id": tid, "tipo": "valores", "es": es, "en": en, "reglas": [], "salida": salida, "estado": "respondida"})
    for tid, es, en, motivo in AMBIGUAS:
        t.append({"id": tid, "tipo": "ambigua", "es": es, "en": en, "reglas": [], "salida": {}, "estado": "requiere_aclaracion", "motivo": motivo})
    for tid, es, en, motivo in SIN_RESPUESTA:
        t.append({"id": tid, "tipo": "sin_respuesta", "es": es, "en": en, "reglas": [], "salida": {}, "estado": "abstenida", "motivo": motivo})
    for x in t:
        x["pasos_min"] = PASOS_MIN[x["tipo"]] + max(0, len(x["salida"]) - 1)
        x["herramientas_min"] = HERRAMIENTAS[x["tipo"]]
    return t


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--solo-listar", action="store_true")
    a = ap.parse_args()
    tareas = tareas_base()
    if a.solo_listar:
        for x in tareas:
            print(x["id"], x["tipo"], "|", x["es"])
        return
    cmp = cargar_comparador()
    conn = cmp.conectar(os.environ["PG_DSN"])
    with conn.cursor() as cur:
        cur.execute("SET search_path = copilot, public")
    fallas, vacias = [], []
    for x in tareas:
        for clave, s in x["salida"].items():
            try:
                filas = cmp.ejecutar(conn, s["sql"])
            except Exception as e:  # noqa: BLE001
                fallas.append(f"{x['id']}.{clave}: {e}")
                conn.rollback() if not conn.autocommit else None
                continue
            norm = cmp.normalize_rows(filas)
            if s["tipo"] in ("numero", "texto") and (len(norm) != 1 or len(norm[0]) != 1):
                fallas.append(f"{x['id']}.{clave}: se esperaba 1 valor y hubo {len(norm)} filas")
            if s["tipo"] == "conjunto" and norm and len(norm[0]) != 1:
                fallas.append(f"{x['id']}.{clave}: el conjunto debe tener 1 columna")
            if not norm or (s["tipo"] in ("numero",) and norm[0][0] in (0, 0.0)):
                vacias.append(f"{x['id']}.{clave}")
            s["esperado"] = [list(r) for r in norm]
    with conn.cursor() as cur:
        cur.execute("SELECT (SELECT MAX(day) FROM sales_daily), (SELECT COUNT(*) FROM products), (SELECT COUNT(*) FROM stock),"
                    " (SELECT COUNT(*) FROM sales_daily), (SELECT COUNT(*) FROM purchase_orders), (SELECT COUNT(*) FROM suppliers)")
        corte, n_p, n_s, n_v, n_o, n_pr = cur.fetchone()
    if fallas:
        print("FALLAS:\n  " + "\n  ".join(fallas))
        sys.exit(1)
    for lang in ("es", "en"):
        with open(AQUI / f"tareas_{lang}.jsonl", "w", encoding="utf-8") as f:
            for x in tareas:
                salida = {c: {"tipo": s["tipo"], "descripcion": s[lang], "orden": s["orden"], "sql_ref": s["sql"], "esperado": s["esperado"]}
                          for c, s in x["salida"].items()}
                f.write(json.dumps({"id": f"{x['id']}-{lang}", "lang": lang, "tipo": x["tipo"], "tarea": x[lang],
                                    "estado_esperado": x["estado"], "salida": salida, "reglas": x["reglas"],
                                    "pasos_min": x["pasos_min"], "herramientas_min": x["herramientas_min"],
                                    **({"origen": x["origen"]} if "origen" in x else {}),
                                    **({"motivo": x["motivo"]} if "motivo" in x else {})}, ensure_ascii=False) + "\n")
    conteo = {}
    for x in tareas:
        conteo[x["tipo"]] = conteo.get(x["tipo"], 0) + 1
    manifiesto = {
        "descripcion": "Golden set de tareas del agente, semana 13. Congelado: cualquier cambio exige regenerar y revisar en PR.",
        "tareas_por_idioma": len(tareas), "por_tipo": conteo,
        "claves_de_salida": sum(len(x["salida"]) for x in tareas),
        "datos": {"fecha_corte": str(corte), "products": n_p, "stock": n_s, "sales_daily": n_v, "purchase_orders": n_o, "suppliers": n_pr},
        "resultados_vacios_o_cero": vacias,
        "sha256": {p: sha(AQUI / p) for p in ("tareas_es.jsonl", "tareas_en.jsonl", "reglas_negocio.json", "construir_tareas.py")},
    }
    (AQUI / "manifiesto.json").write_text(json.dumps(manifiesto, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"Tareas por idioma: {len(tareas)} {conteo}. Claves de salida: {manifiesto['claves_de_salida']}. Fecha de corte: {corte}.")
    print("Resultados vacíos o en cero (revisar):", vacias or "ninguno")


if __name__ == "__main__":
    main()
