"""Práctica semana 2: cuántos tokens cuesta el mismo texto en español y en inglés.

Tres conteos:
- Qwen: tokenizador oficial de Qwen2.5 (conteo exacto con ese tokenizador).
- Claude: conteo oficial de la API si hay ANTHROPIC_API_KEY; si no, estimación con tiktoken (declarada).
- Tokenizador abierto: tiktoken o200k_base (conteo exacto con ese tokenizador).
"""
import os
from pathlib import Path

import tiktoken
from transformers import AutoTokenizer

ES = Path("texto_es.txt").read_text(encoding="utf-8")
EN = Path("texto_en.txt").read_text(encoding="utf-8")

# Precio por millón de tokens de entrada (USD). Llénalo con la tabla vigente del proveedor.
PRECIO_POR_MTOK = {"Claude": 2.0, "Qwen": None, "tiktoken": None}  # USD por millón de tokens de entrada (claude-sonnet-5-5)

resultados = {}  # nombre -> (tokens_es, tokens_en, etiqueta de método)

# 1. Tokenizador abierto (exacto)
enc = tiktoken.get_encoding("o200k_base")
resultados["tiktoken"] = (len(enc.encode(ES)), len(enc.encode(EN)), "exacto (o200k_base)")

# 2. Qwen (exacto con su tokenizador)
qtok = AutoTokenizer.from_pretrained("Qwen/Qwen2.5-7B-Instruct")
resultados["Qwen"] = (len(qtok.encode(ES)), len(qtok.encode(EN)), "exacto (Qwen2.5)")

# 3. Claude: oficial si hay clave; si no, estimación declarada
if os.getenv("ANTHROPIC_API_KEY"):
    import anthropic

    client = anthropic.Anthropic()

    def contar(texto):
        r = client.messages.count_tokens(
            model="claude-sonnet-5-5",
            messages=[{"role": "user", "content": texto}],
        )
        return r.input_tokens

    # Overhead fijo del formato del mensaje: la letra "a" pesa 1 token.
    overhead = contar("a") - 1
    print(f"overhead de formato de Claude: {overhead} tokens (se restan de cada conteo)")
    resultados["Claude"] = (
        contar(ES) - overhead,
        contar(EN) - overhead,
        f"oficial (API), sin {overhead} tokens de formato",
    )
else:
    resultados["Claude"] = (
        len(enc.encode(ES)),
        len(enc.encode(EN)),
        "ESTIMACIÓN: proxy con o200k_base, no oficial",
    )

print(f"{'tokenizador':<12} | {'ES':>6} | {'EN':>6} | {'ES/EN':>6} | {'extra ES':>8} | método")
for nombre, (es, en, metodo) in resultados.items():
    print(f"{nombre:<12} | {es:>6} | {en:>6} | {es / en:>6.2f} | {(es - en) / en:>7.0%} | {metodo}")

print("\nCosto por texto (solo si llenas PRECIO_POR_MTOK):")
for nombre, (es, en, _) in resultados.items():
    precio = PRECIO_POR_MTOK.get(nombre)
    if precio:
        print(f"{nombre:<12} ES: ${es / 1e6 * precio:.6f}  EN: ${en / 1e6 * precio:.6f}")
