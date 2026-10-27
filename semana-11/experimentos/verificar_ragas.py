"""Semana 11, pendiente previo: verifica RAGAS con un juez de Anthropic y embeddings bge-m3 de LM Studio.

Registra versiones y corre 4 métricas de RAGAS (API moderna, ragas.metrics.collections) sobre 4 casos con
resultado conocido, construidos con un pasaje literal de semana-08/corpus/devoluciones.md:
- fiel: respuesta correcta y apoyada en el contexto (faithfulness y answer relevance altas);
- cifra_cambiada: "45 días" en lugar de "30 días" (faithfulness debe bajar);
- fuera_de_tema: respuesta cierta pero que no contesta la pregunta (answer relevance debe bajar);
- contexto_equivocado: contexto sin el pasaje de referencia (context recall debe bajar).
No es la meta-evaluación de la actividad 3 (eso usa 20 preguntas por idioma): solo confirma que la configuración
funciona y que las métricas se mueven en la dirección esperada. Registra tokens y costo del juez.

Configuración:
- Juez: llm_factory(modelo, provider="anthropic", client=AsyncAnthropic()). Las métricas de ragas.metrics.collections
  llaman a agenerate(), así que el cliente tiene que ser asíncrono (con Anthropic() fallan con TypeError). RAGAS manda por defecto temperature=0.01
  y top_p=0.1; los modelos Claude actuales no aceptan ambos, así que se quitan los dos. El esfuerzo va en
  extra_body.output_config (default de Haiku: medium) y max_tokens sube a 4000 porque el razonamiento cuenta como salida.
- Embeddings: embedding_factory("openai", model=LMSTUDIO_EMBED_MODEL, client=AsyncOpenAI(base_url=LM Studio)).
Requiere ANTHROPIC_API_KEY y LM Studio con bge-m3. Uso: python verificar_ragas.py [--modelo ...] [--esfuerzo low]
"""
import argparse
import importlib.metadata as md
import json
import os
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
PRECIOS = json.loads((REPO / "semana-07" / "prices.json").read_text(encoding="utf-8"))

PREGUNTA = "¿Cuál es el plazo para que un cliente devuelva un producto?"
REFERENCIA = "El cliente tiene 30 días naturales desde la entrega para devolver un producto."
CONTEXTO = ["- Plazo: **30 días naturales** desde la entrega.\n- El producto debe estar en su empaque original y sin uso.\n"
            "- La nota de crédito se emite en un máximo de **10 días hábiles** después de recibir la devolución."]
CONTEXTO_OTRO = ["- Por defecto de calidad: dentro de los **15 días** siguientes a la recepción.\n"
                 "- Por exceso de entrega: se devuelve la diferencia o se negocia su aceptación con nota de cargo."]
CASOS = {
    "fiel": (CONTEXTO, "El plazo es de 30 días naturales desde la entrega, con el producto en su empaque original y sin uso."),
    "cifra_cambiada": (CONTEXTO, "El plazo es de 45 días naturales desde la entrega."),
    "fuera_de_tema": (CONTEXTO, "La nota de crédito se emite en un máximo de 10 días hábiles."),
    "contexto_equivocado": (CONTEXTO_OTRO, "No tengo ese dato en el contexto."),
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--modelo", default="claude-haiku-5-5")
    ap.add_argument("--esfuerzo", default="low", choices=["low", "medium", "high"])
    args = ap.parse_args()

    for pkg in ("ragas", "langchain-community", "langchain-core", "instructor", "anthropic", "openai"):
        try:
            print(f"{pkg}=={md.version(pkg)}")
        except md.PackageNotFoundError:
            print(f"{pkg}: no instalado")

    from anthropic import AsyncAnthropic
    from openai import AsyncOpenAI
    from ragas.embeddings.base import embedding_factory
    from ragas.llms import llm_factory
    from ragas.metrics.collections import AnswerRelevancy, ContextRecall, Faithfulness

    uso = {"in": 0, "out": 0, "llamadas": 0}
    cliente = AsyncAnthropic()
    crear = cliente.messages.create

    async def crear_contando(*a, **k):
        r = await crear(*a, **k)
        uso["in"] += r.usage.input_tokens
        uso["out"] += r.usage.output_tokens
        uso["llamadas"] += 1
        return r
    cliente.messages.create = crear_contando

    juez = llm_factory(args.modelo, provider="anthropic", client=cliente, max_tokens=4000,
                       extra_body={"output_config": {"effort": args.esfuerzo}})
    juez.model_args.pop("temperature", None)
    juez.model_args.pop("top_p", None)
    print(f"juez: {args.modelo} ({args.esfuerzo}); argumentos: {juez.model_args}")

    base = os.getenv("LMSTUDIO_BASE_URL", "http://localhost:1234/v1")
    modelo_emb = os.getenv("LMSTUDIO_EMBED_MODEL", "text-embedding-bge-m3")
    emb = embedding_factory("openai", model=modelo_emb, client=AsyncOpenAI(base_url=base, api_key="lm-studio"))
    print(f"embeddings: {modelo_emb} en {base}")

    metricas = {"faithfulness": Faithfulness(llm=juez), "answer_relevancy": AnswerRelevancy(llm=juez, embeddings=emb),
                "context_recall": ContextRecall(llm=juez)}
    print("\n| Caso | faithfulness | answer_relevancy | context_recall | segundos |")
    print("|---|---|---|---|---|")
    for nombre, (ctx, resp) in CASOS.items():
        t0 = time.perf_counter()
        f = metricas["faithfulness"].score(user_input=PREGUNTA, response=resp, retrieved_contexts=ctx).value
        r = metricas["answer_relevancy"].score(user_input=PREGUNTA, response=resp).value
        c = metricas["context_recall"].score(user_input=PREGUNTA, retrieved_contexts=ctx, reference=REFERENCIA).value
        print(f"| {nombre} | {f:.2f} | {r:.2f} | {c:.2f} | {time.perf_counter() - t0:.1f} |")
    p = PRECIOS[f"anthropic:{args.modelo}"]
    print(f"\nJuez: {uso['llamadas']} llamadas, {uso['in']} tokens de entrada y {uso['out']} de salida; "
          f"costo ${(uso['in'] * p['in'] + uso['out'] * p['out']) / 1e6:.5f}")
    esperado = ("Esperado: fiel con faithfulness y relevance altas; cifra_cambiada con faithfulness baja; "
                "fuera_de_tema con relevance más baja que fiel; contexto_equivocado con context_recall baja.")
    print(esperado, file=sys.stderr)


if __name__ == "__main__":
    main()
