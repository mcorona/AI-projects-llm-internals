import mlx.core as mx
import mlx.nn as nn

mx.random.seed(0)
B, T, C, H = 2, 8, 16, 16   # batch, tokens, canal de entrada, dimensión de la cabeza

x = mx.random.normal((B, T, C))

Wq = nn.Linear(C, H, bias=False)
Wk = nn.Linear(C, H, bias=False)
Wv = nn.Linear(C, H, bias=False)

q, k, v = Wq(x), Wk(x), Wv(x)            # cada una: (B, T, H)

# Puntuaciones de atención: (B, T, T)
scores = (q @ k.transpose(0, 2, 1)) / (H ** 0.5)

# Máscara causal: el token i solo puede mirar los j <= i
mask = mx.triu(mx.full((T, T), -mx.inf), k=1)
weights = mx.softmax(scores + mask, axis=-1)
out = weights @ v                         # (B, T, H)

print("forma de salida:", out.shape)
print("cada fila de pesos suma 1:", mx.allclose(weights.sum(-1), mx.ones((B, T))).item())
print("pesos del token 0 (solo se ve a sí mismo):", weights[0, 0, :4].tolist())

# Comparación con la implementación optimizada de MLX
ref = mx.fast.scaled_dot_product_attention(
    q[:, None], k[:, None], v[:, None], scale=H ** -0.5, mask="causal"
)[:, 0]
print("coincide con mx.fast:", mx.allclose(out, ref, atol=1e-5).item())