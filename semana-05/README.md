# Semana 5: prompting multi-modelo y biblioteca de prompts versionada

Objetivo: tratar cada prompt como código. Cada plantilla vive en Git con versión, ejemplos few-shot, formato de salida validable y un comando reproducible para ejecutarla.

## Estructura

| Archivo | Contenido |
|---|---|
| `prompts/resumen_negocio.json` | Salida con formato fijo (tres viñetas) y regla de respaldo `INSUFICIENTE` |
| `prompts/extraccion_json.json` | Extracción a JSON válido, con un ejemplo few-shot y validación con `json.loads` |
| `prompts/clasificacion_intencion.json` | Clasificación en etiquetas cerradas, con dos ejemplos few-shot y validación contra la lista |
| `prompts/consulta_inventario.json` | Tool use básico: el modelo decide llamar `buscar_sku` con un esquema JSON |
| `prompts/_compartido/contexto_logistica.md` | Contexto de dominio común (glosario, reglas, casos resueltos). Se antepone al sistema de cada plantilla; es la parte estable que se cachea |
| `run_prompts.py` | Ejecutor sin dependencias externas (solo biblioteca estándar de Python) |
| `resultados/ejecuciones.jsonl` | Registro de cada ejecución: versión de la plantilla, modelo, latencia, tokens, validación y salida |

Cada plantilla es un JSON con: `nombre`, `version`, `contexto` (ruta al contexto compartido), `sistema`, `usuario` (con variables `{variable}`), `ejemplos`, `herramientas` (opcional) y `validar`.

Reglas de `validar`:
- `"json"`: la salida debe parsear como JSON.
- `{"etiquetas": [...]}`: la salida debe ser exactamente una de las etiquetas.
- `{"resumen": {"vinetas": 3, "max_palabras": 25, "respuesta_exacta": "INSUFICIENTE"}}`: tres líneas con `- `, máximo 25 palabras cada una, o la respuesta exacta de respaldo.

## Cómo correr

```bash
cd semana-05

# Ver la petición sin llamar a la API
python3 run_prompts.py clasificacion_intencion --var "mensaje=¿Dónde va mi pedido 88421?" --dry-run

# Ejecutar (requiere ANTHROPIC_API_KEY en el entorno)
set -a; . ../.env; set +a
python3 run_prompts.py extraccion_json --var "correo=Requerimos 60 piezas del SKU LT-9 antes del 3 de diciembre de 2026. Carlos Peña, Refaccionaria Sur."
```

Para variables largas se usa `--archivo variable=ruta.txt` en lugar de `--var`.

## Decisiones

- **Modelo por defecto:** `claude-haiku-5-5`. No se envía `temperature`, porque este modelo solo acepta el valor 1.
- **Prompt caching:** el bloque `system` lleva `cache_control`. El contexto compartido (unos 9.900 caracteres, aprox. 2.800 tokens) va primero, para que la parte fija sea un prefijo cacheable. El registro guarda `tokens_cache_escritura` y `tokens_cache_lectura` para medir el efecto.
- **Sin dependencias:** el ejecutor usa `urllib` para no depender de SDKs. Así un cambio de SDK no altera los resultados de la biblioteca.
- **Versionado:** una plantilla cambia de versión cuando cambia su comportamiento esperado. El registro conserva la versión usada en cada corrida, para poder comparar antes y después.


## Comparación de proveedores (una muestra por celda)

Las cuatro plantillas se corrieron con Anthropic (`claude-haiku-5-5`), OpenAI (`gpt-5.6-luna` y `gpt-5.6-terra`) y Gemini (`gemini-3.8-flash`).

| Plantilla | Anthropic | OpenAI (luna) | Gemini (3.8 flash) |
|---|---|---|---|
| `resumen_negocio` | Válida, 4.11 s, entrada 138 + caché escritura 3.852, salida 303 | Válida, 3.41 s, entrada 2.307, salida 175 | Válida, 7.00 s, entrada 2.334, salida 58 |
| `clasificacion_intencion` | `cotizacion`, válida, 1.09 s, entrada 139 + caché escritura 3.811, salida 7 | `cotizacion`, válida, 2.43 s, entrada 2.284, salida 5 | `cotizacion`, válida, 1.90 s, entrada 2.307, salida 2 |
| `extraccion_json` | JSON válido, datos correctos, 1.06 s, entrada 255, salida 57 | JSON válido, datos correctos, 1.76 s, entrada 2.391, salida 32 | JSON válido, datos correctos, 4.46 s, entrada 2.438, salida 42 |
| `consulta_inventario` | `buscar_sku` con `AX-204`, 0.95 s, entrada 97, salida 54 | `buscar_sku` con `AX-204`, 2.07 s, entrada 2.346, salida 20 | `buscar_sku` con `AX-204`, 2.87 s, entrada 2.305, salida 20 |

Resultados de `gpt-5.6-terra` (misma entrada que luna, una muestra por plantilla):

| Plantilla | OpenAI (terra) |
|---|---|
| `clasificacion_intencion` | `cotizacion`, válida, 2.25 s, entrada 2.284, salida 5 |
| `resumen_negocio` | Válida, 1.75 s, entrada 2.307, salida 54 |
| `extraccion_json` | JSON válido, datos correctos, 1.03 s, entrada 2.391, salida 32 |
| `consulta_inventario` | `buscar_sku` con `AX-204`, 1.56 s, entrada 2.346, salida 20 |

Notas de lectura:

- En OpenAI, `consulta_inventario` necesita `reasoning_effort: "none"`. Sin eso, `gpt-5.6-luna` rechaza la herramienta con HTTP 400 en `chat/completions`. El ejecutor ya lo incluye.
- Los tokens de entrada no son comparables tal cual: el contexto compartido (unos 2.300 tokens) lo cuenta OpenAI y Gemini como entrada, pero Anthropic lo separa en caché de escritura o lectura. Para comparar costo hay que sumar entrada más caché de cada proveedor.
- La caché de Anthropic se escribió en cada plantilla. La lectura solo ocurrió en la segunda corrida de `resumen_negocio`, dentro de 5 minutos.
- Gemini no reporta tokens de caché en estas corridas.
- Los precios de OpenAI (luna: $1.00 / $6.00 por millón; terra: $2.50 / $15.00) vienen de una fuente de terceros y no están verificados en documentación oficial.
- Una muestra por celda no permite concluir calidad ni costo. Sirve para confirmar que cada proveedor funciona con la biblioteca.

## Estado

- Biblioteca: 4 plantillas, validadas en modo `--dry-run` y en corridas reales, incluida la validación de `resumen_negocio` (cuerpo de petición correcto, ejemplos en orden alternado usuario/asistente, herramienta definida).
- Ejecuciones reales contra la API (claude-haiku-5-5, 4 corridas, todas `stop_reason` correcto):
  - `clasificacion_intencion`: `cotizacion` para "¿me dan precio para 500 cajas al mes?". Validación de etiqueta: correcta.
  - `extraccion_json`: JSON válido con cliente, SKU, cantidad y fecha correctos. Validación JSON: correcta.
  - `consulta_inventario`: llamó `buscar_sku` con `{"sku": "AX-204"}`, como se esperaba.
  - `resumen_negocio`: tres viñetas en español, sin introducción. Sin validación automática.
- Caché de prompt verificada: dos corridas seguidas de `resumen_negocio`. La primera escribió 3.852 tokens en caché (`tokens_cache_escritura`) y la segunda los leyó (`tokens_cache_lectura`). En la primera versión sin contexto compartido, la caché quedaba en 0. La diferencia de latencia entre ambas corridas (1.38 s y 1.11 s) es una sola muestra y no sirve como evidencia de mejora.
- Validación de `resumen_negocio`: implementada y probada con seis casos sintéticos (tres viñetas, dos viñetas, sin guion, exceso de palabras, respuesta de respaldo exacta y respaldo con texto extra). Todos pasan.
- Latencias observadas: 0.8 a 2.0 s por llamada. Son cuatro corridas, así que no son un benchmark.
- Comparación multi-modelo: completa. Cuatro plantillas con Anthropic, OpenAI (luna y terra) y Gemini (3.8 flash).
- Clave de API: se lee de `semana-05/.env` (ignorado por Git) o del entorno. No se versiona.
- Eval automática de las plantillas: se construye en la semana 6, sobre `prompt-evaluator`.
