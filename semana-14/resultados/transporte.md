# Activity 3: Streamable HTTP transport

Code: [`servidor/http.py`](../servidor/http.py) and [`servidor/__main__.py`](../servidor/__main__.py). Tests: [`tests/test_transporte.py`](../tests/test_transporte.py). They run against a real uvicorn server on `127.0.0.1` with a free port, using the SDK's HTTP client plus raw `http.client` requests for the cases a correct client never sends. No API calls, $0.

```bash
cd semana-14
python -m servidor --transporte http --puerto 8014 --usuario analista --trazas resultados/trazas/http.jsonl
python -m servidor --transporte stdio --usuario analista      # same server over stdio
```

## Layers (outside to inside)

| Layer | What it enforces | Response |
|---|---|---|
| **Bind** | `127.0.0.1` only. The address is fixed in code and there is no `--host` option | Not reachable from other interfaces (A08) |
| **Front layer** (`Frontera`, own ASGI) | POST only | 405 `Allow: POST` for GET or DELETE: 2026-07-28 has no GET stream and no sessions |
| | Body size, checked against the declared `Content-Length` and while reading chunks (default 256 KB) | 413, before the whole body is read (A13) |
| | Requests in flight (default 16) | 503 `Retry-After: 1` instead of an unbounded queue (A13) |
| | `MCP-Protocol-Version` header vs the body's `_meta` | 400 `-32020` (see the finding below) |
| | One JSONL trace per request | Always written, including rejected requests |
| **SDK Streamable HTTP** | `Host` against `127.0.0.1:<port>` and `localhost:<port>` | 421 |
| | `Origin` against the same two origins | 403 (A08: DNS rebinding) |
| | `Mcp-Method` and `Mcp-Name` against the body; missing headers | 400 `HeaderMismatch` `-32020` (A11) |
| | Stateless (`stateless_http=True`) and JSON responses | No `Mcp-Session-Id`, even for a client that sends the 2025-11-25 `initialize` |
| **Tools** (`LimitesHerramientas`) | Each call runs in a thread so it does not block the event loop. At most 4 run at once, and each has a 15 s limit (the database adds `statement_timeout` of 5 s) | On timeout: structured error `tiempo_agotado`, valid against the `outputSchema` |

## Traces (reused in week 17)

There is one line per request. The fields are:
- `ts`, `http`, `ruta`
- `metodo` and `nombre` (tool, URI or prompt)
- `sujeto` and `scopes`
- `cliente` and `protocolo`
- `estado` (HTTP)
- `resultado`, one of: `ok`, `error_herramienta`, `error_protocolo` or `rechazado`
- `error` (the tool's error `tipo`, the JSON-RPC code, or the HTTP status)
- `ms`, `bytes_in` and `bytes_out`

Arguments, results and headers are never logged. `test_trazas_jsonl` sends a secret value as an argument and a `Bearer` token, then checks that neither appears in the file. In this activity, `sujeto` is the user fixed for the process and `scopes` is empty. From activity 5 on, both come from the validated token.

Example ([`trazas_http_ejemplo.jsonl`](trazas_http_ejemplo.jsonl), user `almacenista`):

| method / name | HTTP | result | error |
|---|---|---|---|
| `server/discover`, `tools/list`, `resources/list`, `resources/read legado://esquema/artmst`, `prompts/get`, `tools/call describir_esquema`, `tools/call buscar_regla_negocio` | 200 | ok | |
| `tools/call validar_sql` (`prvmst`), `tools/call proponer_orden_compra` | 200 | error_herramienta | permiso_denegado |
| `tools/list` with a hostile `Origin` | 403 | rechazado | 403 |
| body over 4 KB | 413 | rechazado | 413 |
| `Mcp-Name` different from the body | 400 | error_protocolo | -32020 |
| GET | 405 | rechazado | 405 |

## Equivalence: HTTP, stdio and in-memory

`structuredContent`, `isError` and `_meta` source are identical across the three transports:
- The cases without a database are the 18 from activity 2, for `analista` and `almacenista`.
- The cases with the legacy database are the 17 from activity 2, including a timeout, truncation and permission denied.

The stdio server is a separate process (`python -m servidor --transporte stdio`) that inherits the same database role.

Latency of `buscar_regla_negocio` (200 calls, no database, measured in the cloud container):

| Transport | p50 | p95 |
|---|---|---|
| In-memory | 2.7 ms | 3.4 ms |
| stdio | 3.8 ms | 5.2 ms |
| Streamable HTTP | 15.6 ms | 20.8 ms |

HTTP adds about 12 ms per call (TCP, the front layer, a thread per call and JSON). That is negligible next to a model call: the week 13 p50 is 10.2 s per task.

## Results

| Run | Result |
|---|---|
| `pytest semana-14/tests` with the legacy database | **55 passed**, 12 skipped (threat-matrix rows still `planned`) |
| Without a database | 51 passed, 16 skipped |
| `test_transporte.py`, 5 consecutive runs (flakiness check for the timing and concurrency tests) | 13/13 each time |
| `pytest semana-13/tests` with the database (no regression) | 106 passed, 1 skipped |
| `verificar_sdk.py` | 24/24 |

## Findings

- **The SDK routes by header and skips one check.** With a handshake-era `MCP-Protocol-Version` (2025-11-25) and a body whose `_meta` says 2026-07-28, the SDK treated the request as legacy and executed it. The specification requires `400 HeaderMismatch` when the header and the `_meta` disagree. The front layer now enforces it (`test_mcp_name_distinto_400`, "version different from `_meta`" case). This matters if a proxy applies policy based on headers (A11). Threat A11 is now `covered`.
- **The tool call blocked the event loop.** In activity 2, `Herramientas.llamar` (synchronous, with database I/O) ran inside the async handler. Over HTTP that serialized every request and the time limit could not fire. Calls now run in threads with a `CapacityLimiter`. `test_concurrencia_de_herramientas_limitada` shows that at most 2 of 6 simultaneous calls run (limit 2), and `test_tiempo_agotado` answers in less than 1.5 s against a tool that takes 2 s.
- **A timed-out thread is abandoned, not killed.** Python cannot cancel a thread that is already running. The database bounds its work with `statement_timeout` (5 s), and the front layer bounds new work with the in-flight limit.
- **DNS rebinding is covered at the transport level, but A08 stays `planned`.** Its mitigation also requires authentication on every request, which arrives in activity 5.
