"""Actividad 8: respuesta con citas sobre el top 5 (vectorial + reranking con Haiku) y evaluación.

Por idioma: exactitud (juez Haiku: la respuesta contiene el dato de los pasajes de referencia),
precisión de citas (la cita [n] apunta a un chunk que contiene un pasaje de referencia),
respuestas sin cita, y costo por respuesta (rerank + respuesta + juez).
"""
import json
import re
import sys
from pathlib import Path

AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI))
import reranking as rk  # noqa: E402
from embeddings_comparacion import emb_bge  # noqa: E402

RAIZ = AQUI.parents[0]
TOP = 5
SISTEMA_RESP = ("Responde solo con la información de los pasajes. Cita con [n] el pasaje en el que te apoyas. "
                "Si los pasajes no contienen la respuesta, di: No encuentro esa información en los pasajes. "
                "Responde en el mismo idioma de la pregunta, en pocas frases.")
SISTEMA_JUEZ = ("Eres un juez. Decides si la respuesta contiene el dato que indican los pasajes de referencia. "
                "Responde SOLO con JSON: {\"correcta\": true} o {\"correcta\": false}.")


def llamar(sistema, usuario):
    cuerpo = {"model": rk.MODELO, "max_tokens": 4096, "system": sistema,
              "messages": [{"role": "user", "content": usuario}]}
    r = rk.http("POST", "https://api.anthropic.com/v1/messages", cuerpo, {
        "x-api-key": rk.os.environ["ANTHROPIC_API_KEY"], "anthropic-version": "2023-06-01"})
    texto = "".join(b.get("text", "") for b in r["content"] if b.get("type") == "text")
    return texto, r["usage"]["input_tokens"], r["usage"]["output_tokens"]


def top_reordenado(consulta, cands):
    orden, a, b = rk.llamar_haiku(consulta, cands)
    if orden is None:
        return cands[:TOP], a, b, True
    ordenados = list(dict.fromkeys(orden))
    resto = [i for i in range(len(cands)) if i not in ordenados]
    return [cands[i] for i in (ordenados + resto)[:TOP]], a, b, False


def main():
    for idioma in ("es", "en"):
        consultas = [json.loads(l) for l in
                     (RAIZ / "datasets" / f"recuperacion_{idioma}.jsonl").read_text(encoding="utf-8").splitlines()]
        vq, _ = emb_bge([q["question"] for q in consultas], "query")
        correctas = incorrectas = fallos_juez = sin_cita = 0
        cit_total = cit_buenas = 0
        tin = tout = 0
        for q, v in zip(consultas, vq):
            cands = rk.buscar_vectorial(v, 20)
            top, a1, b1, _ = top_reordenado(q["question"], cands)
            tin, tout = tin + a1, tout + b1
            bloque = "\n\n".join(f"[{i + 1}] {c}" for i, (_, c) in enumerate(top))
            resp, a2, b2 = llamar(SISTEMA_RESP, f"Pregunta: {q['question']}\n\nPasajes:\n{bloque}")
            tin, tout = tin + a2, tout + b2
            refs = "\n".join(f"- {g['passage']}" for g in q["gold"])
            texto, a3, b3 = llamar(SISTEMA_JUEZ,
                                   f"Pregunta: {q['question']}\nRespuesta: {resp}\nPasajes de referencia:\n{refs}")
            tin, tout = tin + a3, tout + b3
            m = re.search(r"\{.*\}", texto, re.S)
            try:
                ok = bool(json.loads(m.group(0))["correcta"])
            except (AttributeError, json.JSONDecodeError, KeyError, TypeError):
                ok = None
                fallos_juez += 1
            if ok:
                correctas += 1
            else:
                incorrectas += 1
            nums = [int(n) for n in re.findall(r"\[(\d+)\]", resp) if 1 <= int(n) <= len(top)]
            if not nums:
                sin_cita += 1
            for n in nums:
                cit_total += 1
                src, cont = top[n - 1]
                if any(src == g["source"] and g["passage"] in cont for g in q["gold"]):
                    cit_buenas += 1
        n = len(consultas)
        costo = (tin * rk.PRECIO["in"] + tout * rk.PRECIO["out"]) / 1e6
        print(f"{idioma} exactitud={correctas / n:.3f} ({correctas}/{n}) "
              f"precision_citas={(cit_buenas / cit_total) if cit_total else 0:.3f} "
              f"sin_cita={sin_cita} fallos_juez={fallos_juez} "
              f"costo_por_respuesta=${costo / n:.6f}")


if __name__ == "__main__":
    main()
