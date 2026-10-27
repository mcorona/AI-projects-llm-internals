"""Semana 11, actividad 3: validación de las métricas de generación (meta-evaluación).

Muestra: 20 preguntas por idioma (las mismas en ES y EN), 15 base y 5 no textuales, elegidas con semilla 11 entre las
respondibles cuya referencia trae al menos una cifra que no viene de la pregunta. Contexto: el top 5 del pipeline adoptado de la actividad 2
(resultados/suite_recuperacion_cache.json); todas tienen su pasaje en ese top 5.

Variantes de respuesta (construidas con reglas fijas, sin modelo):
- control: la referencia de la actividad 1 (fiel y pertinente).
- cifra_cambiada: la primera cifra de la referencia que no viene de la pregunta (de preferencia, una del contexto; nunca un año),
  × 1.5 (o × 2, 3, 5, 7, 10, 0.9, 0.5 si el valor nuevo ya aparece en el contexto o la pregunta, o si un
  porcentaje pasaría de 100), con el mismo formato.
- inventada: la referencia más una oración plausible que no está en el contexto (plantilla fija por idioma).
- fuera_de_tema: la referencia de otra pregunta de la muestra, de otro documento (cierta, pero no responde).
- evasiva: una negativa genérica ("No tengo suficiente información…").

Métricas, por juez (Haiku 5.5 low y Sonnet 5.5 low): faithfulness y answer relevancy de RAGAS 0.4.3 (embeddings
bge-m3 de LM Studio), y exactitud con el juez propio de semanas 8 y 10 (SIS_JUEZ de semana-10/experimentos/asistente.py).

Criterios, fijados antes de correr:
- Una métrica detecta una variante si la diferencia pareada variante − control tiene IC bootstrap 95 % (2,000
  remuestreos, semilla 11) por debajo de 0 y la variante queda abajo del control en al menos 80 % de las preguntas
  (empates cuentan 0.5).
- Detecciones esperadas: faithfulness detecta cifra_cambiada e inventada; answer relevancy detecta fuera_de_tema y
  evasiva. El control debe tener faithfulness media >= 0.9.
- Decisión: el juez más barato que cumpla las cuatro detecciones esperadas y el control. Si ninguno cumple todo, el
  que cumpla más, con lo que falta documentado.
Caché por juez, métrica, pregunta y variante en resultados/meta_evaluacion_cache.json (y caché en disco del juez).
Requiere LM Studio con bge-m3 y ANTHROPIC_API_KEY.
"""
import asyncio
import csv
import json
import random
import re
import statistics
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
REPO = RAIZ.parent
RES = RAIZ / "resultados"
CACHE = RES / "meta_evaluacion_cache.json"
PRECIOS = json.loads((REPO / "semana-07" / "prices.json").read_text(encoding="utf-8"))
JUECES = {"haiku": "claude-haiku-5-5", "sonnet": "claude-sonnet-5-5"}
VARIANTES = ("control", "cifra_cambiada", "inventada", "fuera_de_tema", "evasiva")
ESPERADAS = {("faithfulness", "cifra_cambiada"), ("faithfulness", "inventada"),
             ("answer_relevancy", "fuera_de_tema"), ("answer_relevancy", "evasiva")}
CONCURRENCIA = 8
INVENTADA = {"es": "Además, esta regla solo aplica a pedidos internacionales y requiere la firma del director general.",
             "en": "In addition, this rule applies only to international orders and requires the CEO's signature."}
EVASIVA = {"es": "No tengo suficiente información para responder con precisión.",
           "en": "I don't have enough information to answer precisely."}
SIS_JUEZ = ("Eres un evaluador estricto. Recibes una pregunta, la referencia correcta y la respuesta de un asistente. La "
            "respuesta es correcta si contiene la información esencial de la referencia sin contradecirla (puede agregar "
            "detalles o citas). Si la referencia es una lista o un conjunto de filas, la respuesta debe incluir esos "
            "elementos. Responde SOLO con JSON: {\"correcta\": true} o {\"correcta\": false}.")  # copia de semana 10
NUM = re.compile(r"\d[\d,]*(?:\.\d+)?")


def norm(s):
    return " ".join(s.replace("**", "").lower().split())


def numeros(t):
    return {n.replace(",", "").rstrip(".") for n in NUM.findall(t)}


def cambiar_cifra(texto, contexto, pregunta):
    """Cambia la primera cifra de la referencia que no viene de la pregunta (de preferencia, una que esté en el
    contexto), para que el error caiga en el dato de la respuesta y no en la repetición de la pregunta."""
    en_ctx, en_preg = numeros(contexto), numeros(pregunta)
    cands = [m for m in NUM.finditer(texto) if m.group(0).replace(",", "").rstrip(".") not in en_preg
             and not re.fullmatch(r"(19|20)\d\d", m.group(0).rstrip("."))]  # sin años
    cands = [m for m in cands if m.group(0).replace(",", "").rstrip(".") in en_ctx] or cands
    if not cands:
        raise ValueError(f"sin cifra propia de la respuesta: {texto}")
    m = cands[0]
    crudo = m.group(0).rstrip(".")
    dec = len(crudo.split(".")[1]) if "." in crudo else 0
    valor = float(crudo.replace(",", ""))
    porcentaje = texto[m.start() + len(crudo):].lstrip().startswith("%")
    for factor in (1.5, 2, 3, 5, 7, 10, 0.9, 0.5):
        nuevo = valor * factor if valor else factor
        if porcentaje and nuevo > 100:  # un porcentaje imposible sería demasiado fácil de detectar
            continue
        s = f"{nuevo:,.{dec}f}" if "," in crudo else f"{nuevo:.{dec}f}"
        if s != crudo and s.replace(",", "") not in en_ctx | en_preg:
            return texto[:m.start()] + s + texto[m.start() + len(crudo):]
    raise ValueError(f"no se pudo cambiar la cifra de: {texto}")


def muestra():
    ref = {lang: {x["id"]: x for l in (RAIZ / "datasets" / f"eval_rag_{lang}.jsonl").read_text(encoding="utf-8").splitlines()
                  if (x := json.loads(l))["respondible"]} for lang in ("es", "en")}
    ids = [i for i in ref["es"] if i in ref["en"] and all(numeros(ref[l][i]["referencia"]) - numeros(ref[l][i]["question"])
                                                          for l in ("es", "en"))]
    rnd = random.Random(11)
    elegidos = rnd.sample([i for i in ids if ref["es"][i]["tipo"] == "base"], 15) + \
        rnd.sample([i for i in ids if ref["es"][i]["tipo"] != "base"], 5)
    return ref, elegidos


def construir(ref, elegidos, rec):
    casos = []
    for lang in ("es", "en"):
        fuentes = {i: {Path(g["source"]).stem for g in ref[lang][i]["gold"]} for i in elegidos}
        for n, i in enumerate(elegidos):
            x = ref[lang][i]
            ctx = [c for _, c in rec[f"adoptado::{i}::{lang}"]["ranking"][:5]]
            if not any(norm(g["passage"]) in norm(c) for g in x["gold"] for c in ctx):
                raise SystemExit(f"{i} {lang}: el pasaje no está en el top 5 de la actividad 2")
            otro = next(elegidos[(n + k) % len(elegidos)] for k in range(1, len(elegidos))
                        if not fuentes[elegidos[(n + k) % len(elegidos)]] & fuentes[i])
            respuestas = {"control": x["referencia"],
                          "cifra_cambiada": cambiar_cifra(x["referencia"], "\n".join(ctx), x["question"]),
                          "inventada": x["referencia"].rstrip() + " " + INVENTADA[lang],
                          "fuera_de_tema": ref[lang][otro]["referencia"],
                          "evasiva": EVASIVA[lang]}
            for v in VARIANTES:
                casos.append({"id": i, "lang": lang, "tipo": x["tipo"], "variante": v, "question": x["question"],
                              "referencia": x["referencia"], "respuesta": respuestas[v], "contextos": ctx,
                              "fuera_de_tema_de": otro if v == "fuera_de_tema" else ""})
    return casos


async def evaluar(casos, cache, guardar):
    from anthropic import AsyncAnthropic
    from openai import AsyncOpenAI
    from ragas.cache import DiskCacheBackend
    from ragas.embeddings.base import embedding_factory
    from ragas.llms import llm_factory
    from ragas.metrics.collections import AnswerRelevancy, Faithfulness
    import os

    emb = embedding_factory("openai", model=os.getenv("LMSTUDIO_EMBED_MODEL", "text-embedding-bge-m3"),
                            client=AsyncOpenAI(base_url=os.getenv("LMSTUDIO_BASE_URL", "http://localhost:1234/v1"), api_key="lm-studio"))
    uso, metricas, clientes = {}, {}, {}
    for j, modelo in JUECES.items():
        uso[j] = {"in": 0, "out": 0, "llamadas": 0}
        cliente = AsyncAnthropic()
        crear = cliente.messages.create

        async def crear_contando(*a, _crear=crear, _u=uso[j], **k):
            r = await _crear(*a, **k)
            _u["in"] += r.usage.input_tokens
            _u["out"] += r.usage.output_tokens
            _u["llamadas"] += 1
            return r
        cliente.messages.create = crear_contando
        clientes[j] = cliente
        llm = llm_factory(modelo, provider="anthropic", client=cliente, max_tokens=4000,
                          extra_body={"output_config": {"effort": "low"}},
                          cache=DiskCacheBackend(str(Path.home() / ".cache" / "ragas_semana11")))
        llm.model_args.pop("temperature", None)
        llm.model_args.pop("top_p", None)
        metricas[j] = {"faithfulness": Faithfulness(llm=llm), "answer_relevancy": AnswerRelevancy(llm=llm, embeddings=emb)}
    sem = asyncio.Semaphore(CONCURRENCIA)

    async def juez_propio(j, c):
        r = await clientes[j].messages.create(
            model=JUECES[j], max_tokens=2000, system=SIS_JUEZ, extra_body={"output_config": {"effort": "low"}},
            messages=[{"role": "user", "content": f"Pregunta: {c['question']}\n\nReferencia correcta:\n{c['referencia']}"
                                                  f"\n\nRespuesta del asistente:\n{c['respuesta']}"}])
        t = "".join(b.text for b in r.content if getattr(b, "type", "") == "text")
        m = re.search(r"\{.*?\}", t, re.S)
        return float(bool(json.loads(m.group(0))["correcta"])) if m else None

    async def uno(j, metrica, c):
        k = f"{j}::{metrica}::{c['id']}::{c['lang']}::{c['variante']}"
        if k in cache:
            return
        async with sem:
            try:
                if metrica == "exactitud_propia":
                    v = await juez_propio(j, c)
                elif metrica == "faithfulness":
                    v = (await metricas[j][metrica].ascore(user_input=c["question"], response=c["respuesta"],
                                                           retrieved_contexts=c["contextos"])).value
                else:
                    v = (await metricas[j][metrica].ascore(user_input=c["question"], response=c["respuesta"])).value
                cache[k] = {"valor": v}
            except Exception as e:  # noqa: BLE001
                cache[k] = {"valor": None, "error": type(e).__name__}
        guardar()
    await asyncio.gather(*(uno(j, m, c) for j in JUECES for m in ("faithfulness", "answer_relevancy", "exactitud_propia")
                           for c in casos))
    return uso


def bootstrap(dif, n=2000, semilla=11):
    rnd = random.Random(semilla)
    medias = sorted(statistics.mean(rnd.choice(dif) for _ in dif) for _ in range(n))
    return statistics.mean(dif), medias[int(0.025 * n)], medias[int(0.975 * n) - 1]


def main():
    rec = json.loads((RES / "suite_recuperacion_cache.json").read_text(encoding="utf-8"))
    ref, elegidos = muestra()
    casos = construir(ref, elegidos, rec)
    cache = json.loads(CACHE.read_text(encoding="utf-8")) if CACHE.exists() else {}

    def guardar():
        CACHE.write_text(json.dumps(cache, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"muestra: {elegidos}", file=sys.stderr)
    uso = asyncio.run(evaluar(casos, cache, guardar))
    guardar()

    filas = []
    for c in casos:
        for j in JUECES:
            for m in ("faithfulness", "answer_relevancy", "exactitud_propia"):
                v = cache[f"{j}::{m}::{c['id']}::{c['lang']}::{c['variante']}"]
                filas.append({"juez": j, "metrica": m, "id": c["id"], "lang": c["lang"], "tipo": c["tipo"],
                              "variante": c["variante"], "valor": v["valor"], "error": v.get("error", ""),
                              "respuesta": c["respuesta"]})
    with (RES / "meta_evaluacion_detalle.csv").open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(filas[0].keys()))
        w.writeheader()
        w.writerows(filas)

    def valores(j, m, v, lang=None):
        return {(f["id"], f["lang"]): f["valor"] for f in filas if f["juez"] == j and f["metrica"] == m
                and f["variante"] == v and (lang is None or f["lang"] == lang) and f["valor"] is not None}

    print("## Medias por juez, métrica y variante (ES / EN / ambos)\n")
    print("| Juez | Métrica | " + " | ".join(VARIANTES) + " |")
    print("|---|---|" + "---|" * len(VARIANTES))
    for j in JUECES:
        for m in ("faithfulness", "answer_relevancy", "exactitud_propia"):
            celdas = []
            for v in VARIANTES:
                es, en, ab = (valores(j, m, v, l) for l in ("es", "en", None))
                celdas.append(f"{statistics.mean(es.values()):.2f} / {statistics.mean(en.values()):.2f} / {statistics.mean(ab.values()):.2f}")
            print(f"| {j} | {m} | " + " | ".join(celdas) + " |")

    print("\n## Separación de cada variante contra el control (ambos idiomas, n = 40 pares)\n")
    print("| Juez | Métrica | Variante | Esperada | Diferencia media | IC 95 % | Variante < control | Detecta |")
    print("|---|---|---|---|---|---|---|---|")
    veredicto = {}
    for j in JUECES:
        for m in ("faithfulness", "answer_relevancy", "exactitud_propia"):
            ctl = valores(j, m, "control")
            for v in VARIANTES[1:]:
                var = valores(j, m, v)
                pares = [(ctl[k], var[k]) for k in ctl if k in var]
                dif = [b - a for a, b in pares]
                media, lo, hi = bootstrap(dif)
                tasa = sum(1 if b < a else 0.5 if b == a else 0 for a, b in pares) / len(pares)
                detecta = hi < 0 and tasa >= 0.8
                veredicto[(j, m, v)] = detecta
                print(f"| {j} | {m} | {v} | {'sí' if (m, v) in ESPERADAS else 'no'} | {media:+.3f} | [{lo:+.3f}, {hi:+.3f}] | "
                      f"{tasa:.2f} ({len(pares)}) | {'sí' if detecta else 'no'} |")

    print("\n## Decisión\n")
    for j, modelo in JUECES.items():
        ctl = statistics.mean(valores(j, "faithfulness", "control").values())
        ok = [mv for mv in sorted(ESPERADAS) if veredicto[(j, *mv)]]
        p = PRECIOS[f"anthropic:{modelo}"]
        costo = (uso[j]["in"] * p["in"] + uso[j]["out"] * p["out"]) / 1e6
        errores = sum(1 for f in filas if f["juez"] == j and f["valor"] is None)
        print(f"- {j}: detecciones esperadas {len(ok)}/4 {ok}; faithfulness del control {ctl:.3f} "
              f"({'cumple' if ctl >= 0.9 else 'NO cumple'} >= 0.9); sin puntaje {errores}; costo de esta corrida ${costo:.4f} "
              f"({uso[j]['llamadas']} llamadas, {uso[j]['in']} tokens de entrada y {uso[j]['out']} de salida)")


if __name__ == "__main__":
    main()
