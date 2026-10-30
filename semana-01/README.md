# Semana 1 · Notas de práctica

Proyecto: genai-engineering-lab (antes AI-projects-llm-internals) · Fase 1 (Fundamentos profundos de LLMs)
Referencia: serie Zero to Hero de Andrej Karpathy, en MLX.

## Estado

- [x] Paso 1: MLX instalado. La GPU de Apple Silicon responde (`Device(gpu, 0)`).
- [x] Paso 2: bigram en MLX (`bigram_mlx.py`). Pérdida de 3.3120 a 2.4819.
- [x] Paso 3: una cabeza de atención con máscara causal (`attention_mlx.py`). Pesos del token 0 = `[1, 0, 0, 0]` y coincide con `mx.fast`.
- [x] Paso 4: bloque completo del mini-GPT (`minigpt_mlx.py`). 30 400 parámetros; prueba de causalidad superada.
- [x] Paso 5: entrenamiento con Tiny Shakespeare y registro de pérdida (`train_minigpt_mlx.py`, `perdidas.csv`).

## Cómo leer la pérdida del bigram

La pérdida es la log-verosimilitud negativa promedio: `-log p(siguiente carácter correcto)`, promediada sobre los 228 146 bigramas del dataset. Mientras más baja, mejor.

- **Paso 0 (≈ 3.31):** con pesos aleatorios, el modelo reparte la probabilidad casi igual entre los 27 caracteres. Eso da `ln(27) ≈ 3.30`, así que el valor inicial es el esperado.
- **Paso 199 (≈ 2.48):** la pérdida se estabiliza. Es el límite de un modelo que solo mira el carácter anterior.
- **Interpretación:** `exp(2.48) ≈ 12`. En promedio, el modelo queda dudando entre unos 12 caracteres posibles para el siguiente.

## Por qué la tabla 27×27 equivale a conteos

- Cada fila `i` representa un carácter actual. Sus 27 valores son los logits del siguiente carácter.
- `softmax` sobre cada fila convierte los logits en una distribución de probabilidad.
- Los conteos de bigramas también son una tabla 27×27: `N[i, j]` cuenta cuántas veces aparece `j` después de `i`. Normalizar cada fila de `N` da la misma información que la tabla aprendida.
- El entrenamiento con gradientes llega a una aproximación de esa distribución, porque minimizar la pérdida equivale a maximizar la verosimilitud de los bigramas. Por eso la pérdida final de `bigram_mlx.py` queda cerca de la de `bigram_grad.py`.

## Por qué existe el término de regularización

El término `0.01 * mean(W²)` penaliza pesos grandes. Sin él, los logits de los bigramas raros pueden crecer sin límite para ajustarse a casos específicos, y el modelo queda sobreconfiado. Con 228 mil pares el efecto práctico es pequeño, pero en modelos grandes evita que la pérdida de entrenamiento engañe.

## Glosario de los cuatro conceptos

- **Tokenización BPE:** el texto se convierte en tokens. BPE empieza con caracteres o bytes y fusiona las parejas más frecuentes hasta llegar al tamaño de vocabulario. Un texto en español suele consumir más tokens que el mismo texto en inglés. El mini-GPT de Karpathy usa caracteres; BPE es el paso siguiente.
- **Ventana de contexto:** máximo de tokens que el modelo procesa en una pasada. En el código aparece como `block_size`. El costo de la atención crece con el cuadrado de la longitud.
- **Atención:** cada token calcula `softmax(Q·Kᵀ/√d)·V`. Q busca, K ofrece, V aporta información. La máscara causal impide mirar tokens futuros.
- **KV cache:** guarda las K y V ya calculadas para no recalcularlas al generar. Ocupa memoria: por token, `2 × capas × cabezas_KV × dim_cabeza × bytes`. Con un modelo de 7 000 M parámetros en fp16 y 4 096 tokens, ronda los 2 GB.

## Dudas para repasar

- ¿Qué cambiaría en la pérdida inicial si los pesos fueran todos cero en lugar de aleatorios?
- ¿Por qué la atención causal necesita máscara y el bigram no la necesita?
- ¿Qué parte del costo de generar un token nuevo crece con el contexto: los pesos del modelo o el KV cache?

## Resultados del mini-GPT (paso 5)

Configuración común: tokenización a nivel de carácter, `block=64`, `batch=32`, 2000 pasos, AdamW. Cada corrida guarda su curva en `perdidas_*.csv`.

| Configuración | Val final | Train final | Brecha val-train |
|---|---|---|---|
| n=64, lr=3e-3 | 1.87 | 1.75 | 0.12 |
| n=64, lr=1e-3 | 1.74 | 1.57 | 0.17 |
| n=128, lr=1e-3 | 1.72 | 1.54 | 0.18 |

Conclusiones:
- El learning rate fue el factor dominante. Bajarlo de 3e-3 a 1e-3 mejoró la validación en 0.13. Con el ancho de 128, un `lr` de 3e-3 hace que la pérdida oscile y avance más lento, porque las actualizaciones de Adam se suman sobre más conexiones.
- Con este presupuesto de entrenamiento, pasar de 64 a 128 de ancho solo aporta 0.02 en validación.
- La brecha val-train es casi igual en ambos anchos (0.17 y 0.18). No hay sobreajuste atribuible a la capacidad en 2000 pasos (unas 4 pasadas sobre el texto).
- Para observar sobreajuste hace falta más entrenamiento, por ejemplo 10 000 pasos, y ver si la validación deja de bajar mientras la de entrenamiento sigue cayendo.
- La pérdida de entrenamiento se mide sobre un solo lote y es ruidosa. Para comparaciones finas, medirla con `eval_loss` sobre varios lotes.
- Muestras: las tres corridas producen texto con formato de obra de teatro (personajes en mayúsculas, saltos de línea) y palabras reconocibles, con errores ortográficos típicos de un modelo a nivel de carácter.
- No comparable con el bigram: son datasets distintos (nombres contra Shakespeare, con vocabularios distintos).
- Error encontrado: `LR = 2000` en lugar de `3e-3` hizo que la pérdida explotara (val 9.5e8 y luego NaN). Lección: revisar cada variable de configuración antes de correr el script.

## Práctica: memoria del KV cache y decisión de arquitectura

Script: `practica_kv_cache.py`. Estima la memoria del caché para dos modelos de referencia (8B y 70B, fp16), con distintos largos de contexto y número de usuarios simultáneos.

Resultados clave:
- Caché por token: 128 KB (8B) y 320 KB (70B).
- Caso de referencia: documentos de 60 000 tokens y 50 consultas simultáneas.
  - Modelo 8B: unos 366 GiB de caché.
  - Modelo 70B: unos 915 GiB de caché.
- Pesos en fp16: unos 16 GB (8B) y 140 GB (70B). Con muchas consultas simultáneas, el caché pesa más que los pesos.
- Con RAG y 4 096 tokens por consulta, el caché baja a 25 GiB (8B) y 62.5 GiB (70B).

Decisión: RAG como palanca principal para reducir memoria.

Pérdida que hay que declarar al cliente: respuestas que requieren combinar partes distantes del manual, porque el buscador puede recuperar fragmentos incompletos.

Mitigación y medición:
- Medir **hit@k**: porcentaje de preguntas en las que el fragmento correcto aparece entre los k recuperados.
- Usar preguntas reales del cliente, incluyendo preguntas poco frecuentes y las que cruzan secciones.
- Mantener en contexto fijo, con caché de prefijos, solo las secciones más consultadas. Esa memoria fija también consume caché, así que el ahorro no es total.

## Próximos pasos

1. Semana 2 (desde el 26 de octubre): embeddings, sampling y alucinación. Con el mini-GPT, probar `temp` en 0.5, 0.8 y 1.2 y comparar la muestra.
2. Repetir el entrenamiento con `n_layer=4` o `n_embd=128` y registrar cuánto mejora la validación y cuánto tarda.
3. Responder las dudas de repaso en esta nota antes de la semana 2.
