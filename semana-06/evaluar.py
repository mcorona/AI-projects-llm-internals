#!/usr/bin/env python3
"""Evals de regresión para las plantillas de semana-05.

Checks deterministas por caso y un juez LLM para la fidelidad de los resúmenes.
Compara contra baseline/resultados_base.json y termina con código 1 si hay regresión.
"""
import argparse
import importlib.util
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

RAIZ = Path(__file__).resolve().parent
ROOT = RAIZ.parent
GOLDEN = RAIZ / "golden" / "casos.jsonl"
BASE = RAIZ / "baseline" / "resultados_base.json"
RESULTADOS = RAIZ / "resultados"
RUBRICA = RAIZ / "rubricas" / "fidelidad_resumen.txt"
MODELO = "claude-haiku-5-5"
TOLERANCIA = 0.05
UMBRAL_FIDELIDAD = 4

_spec = importlib.util.spec_from_file_location("run_prompts", ROOT / "semana-05" / "run_prompts.py")
rp = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(rp)


def generar(caso, clave):
    plantilla = rp.cargar_plantilla(caso["plantilla"])
    cuerpo = rp.construir("anthropic", plantilla, caso["variables"], MODELO, 1024)
    crudo = rp.llamar("anthropic", cuerpo, clave, MODELO)
    return rp.interpretar("anthropic", crudo, MODELO), plantilla


def evaluar_caso(caso, salida, plantilla):
    tipo = caso["check"]
    texto = salida["texto"].strip()
    if tipo == "etiqueta":
        return texto == caso["esperado"], {"obtenido": texto}
    if tipo == "json_campos":
        try:
            obtenido = json.loads(texto)
        except json.JSONDecodeError:
            return False, {"obtenido": texto, "error": "json inválido"}
        ok = all(obtenido.get(k) == v for k, v in caso["esperado"].items())
        return ok, {"obtenido": obtenido}
    if tipo == "herramienta":
        llamadas = salida["herramientas"]
        esperado = caso["esperado"]
        if esperado is None:
            return len(llamadas) == 0, {"herramientas": llamadas}
        ok = any(l["nombre"] == esperado["nombre"] and l["entrada"] == esperado["entrada"]
                 for l in llamadas)
        return ok, {"herramientas": llamadas}
    if tipo == "resumen_estructura":
        return rp.validar(texto, plantilla.get("validar")) is True, {"obtenido": texto}
    raise ValueError(f"check desconocido: {tipo}")


def juzgar(documento, resumen, clave):
    prompt = RUBRICA.read_text(encoding="utf-8").replace("{documento}", documento).replace("{resumen}", resumen)
    cuerpo = {"model": MODELO, "max_tokens": 300, "messages": [{"role": "user", "content": prompt}]}
    crudo = rp.llamar("anthropic", cuerpo, clave, MODELO)
    texto = rp.interpretar("anthropic", crudo, MODELO)["texto"]
    try:
        datos = json.loads(texto[texto.index("{"):texto.rindex("}") + 1])
        return int(datos["fidelidad"]), datos.get("motivo", "")
    except (ValueError, KeyError):
        return None, f"respuesta del juez no interpretable: {texto[:120]}"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limite", type=int, help="Corre solo los primeros N casos.")
    parser.add_argument("--actualizar-base", action="store_true",
                        help="Guarda esta corrida como nueva línea base.")
    args = parser.parse_args()

    rp.cargar_env_local()
    clave = os.environ.get("ANTHROPIC_API_KEY", "")
    if not clave:
        sys.exit("Falta ANTHROPIC_API_KEY (entorno o semana-05/.env).")

    casos = [json.loads(linea) for linea in GOLDEN.read_text(encoding="utf-8").splitlines() if linea.strip()]
    if args.limite:
        casos = casos[:args.limite]

    resultados = []
    for caso in casos:
        salida, plantilla = generar(caso, clave)
        ok, detalle = evaluar_caso(caso, salida, plantilla)
        if ok and caso.get("juez"):
            fidelidad, motivo = juzgar(caso["variables"]["documento"], salida["texto"], clave)
            ok = fidelidad is not None and fidelidad >= UMBRAL_FIDELIDAD
            detalle["juez"] = {"fidelidad": fidelidad, "motivo": motivo}
        resultados.append({"id": caso["id"], "plantilla": caso["plantilla"], "ok": ok, **detalle})
        print(f"{'OK   ' if ok else 'FALLA'} {caso['id']}")

    tasa = round(sum(r["ok"] for r in resultados) / len(resultados), 3)
    marca = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    reporte = {"fecha": marca, "modelo": MODELO, "juez": MODELO, "casos": len(resultados),
               "tasa": tasa, "resultados": resultados}
    RESULTADOS.mkdir(exist_ok=True)
    (RESULTADOS / f"eval_{marca}.json").write_text(json.dumps(reporte, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Tasa de aprobación: {tasa} ({sum(r['ok'] for r in resultados)}/{len(resultados)})")

    if args.actualizar_base:
        BASE.parent.mkdir(exist_ok=True)
        BASE.write_text(json.dumps(reporte, ensure_ascii=False, indent=2), encoding="utf-8")
        print("Línea base actualizada.")
        return
    if not BASE.exists():
        print("Sin línea base: no hay comparación de regresión.")
        return

    base = json.loads(BASE.read_text(encoding="utf-8"))
    ok_base = {r["id"] for r in base["resultados"] if r["ok"]}
    regresiones = [r["id"] for r in resultados if r["id"] in ok_base and not r["ok"]]
    caida = round(base["tasa"] - tasa, 3)
    print(f"Línea base: {base['tasa']}. Caída: {caida}. Regresiones: {regresiones or 'ninguna'}")
    if regresiones or caida > TOLERANCIA:
        print("REGRESIÓN: el cambio empeora casos que antes pasaban.")
        sys.exit(1)


if __name__ == "__main__":
    main()
