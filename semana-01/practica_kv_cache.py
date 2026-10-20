# Estimación de memoria del KV cache para una propuesta a cliente.
# Configuraciones aproximadas de modelos abiertos típicos (ilustrativas).
GiB = 1024 ** 3
BYTES = 2  # fp16

modelos = {
    "modelo pequeño (~8B)": dict(capas=32, cabezas_kv=8, dim_cabeza=128),
    "modelo grande (~70B)": dict(capas=80, cabezas_kv=8, dim_cabeza=128),
}
contextos = [4_096, 32_768, 131_072]   # tokens por conversación o documento
usuarios = [1, 10, 100]                # conversaciones simultáneas


def kv_por_token(m):
    return 2 * m["capas"] * m["cabezas_kv"] * m["dim_cabeza"] * BYTES


for nombre, m in modelos.items():
    print(f"\n{nombre}: {kv_por_token(m) / 1024:.0f} KB de caché por token")
    cabecera = " | ".join(f"{u:>3} usuario(s)" for u in usuarios)
    print(f"{'contexto':>10} | {cabecera}")
    for ctx in contextos:
        celdas = " | ".join(
            f"{kv_por_token(m) * ctx * u / GiB:>12.1f} GiB" for u in usuarios
        )
        print(f"{ctx:>10,} | {celdas}")