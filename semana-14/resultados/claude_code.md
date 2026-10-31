# Activity 7 (optional): Claude Code as the MCP client, OAuth by hand

No API cost: Claude Code ran on the subscription (`ANTHROPIC_API_KEY` unset). Server trace: [`trazas/claude_code.jsonl`](trazas/claude_code.jsonl) (no tokens recorded). Probe: [`auth/sonda_aud.py`](../auth/sonda_aud.py). Config: [`.mcp.json`](../.mcp.json).

## Setup

```
python -m servidor --transporte http --oauth --trazas resultados/trazas/claude_code.jsonl
claude mcp add-json --scope project legado-remoto '{"type":"http","url":"http://127.0.0.1:8014/mcp","oauth":{"clientId":"legacybridge-agente","callbackPort":53682}}'
claude mcp login legado-remoto
claude --strict-mcp-config --mcp-config .mcp.json --disallowedTools "Bash,Read,Grep,Glob,WebFetch"
```

No scopes are configured on the client: Claude Code has to discover them. The session is isolated (`--strict-mcp-config`, no shell or file tools) because in a first, non-isolated attempt Claude Code answered from a direct database connection instead of the MCP server. **MCP authorization protects nothing if the client has another route to the data.**

## Results

| Test | Expected | Observed (server trace) | ✅ |
|---|---|---|---|
| Discovery | Claude Code finds Keycloak from the server alone | `GET /.well-known/oauth-protected-resource/mcp` → 200, then the authorization request to Keycloak with PKCE S256, `resource=http://127.0.0.1:8014/mcp` (RFC 8707) and redirect `http://localhost:53682/callback` | ✅ |
| Scopes | Least privilege | It requests only what the metadata advertises (`legado:leer`) plus `offline_access`, even for `analista` | ✅ |
| Protocol | 2026-07-28 | `server/discover`, `tools/list`, `tools/call` with `MCP-Protocol-Version: 2026-07-28`. Before having a token it also probed `initialize` 2025-11-25 (fallback after the 401) | ✅ |
| A: `analista`, allowed question | Answer from the server | 4 `tools/call` → 200, "30 critical SKUs" | ✅ |
| A2: `analista`, supplier question | Denial, no leak | `tabla_no_disponible` (`prvmst`) and `permiso_denegado` (`art_prv`); the token carries only `legado:leer`, so even the analyst gets the basic database role. Claude Code did not try to get around it | ✅ |
| B: `almacenista`, supplier question | Denial, no leak | Different subject, `tabla_no_disponible`; `artmst` shows no supplier column at all | ✅ |
| C: token refresh | Keeps working after the 5-minute access token expires | `tools/call` at 20:00:08 with the token issued around 19:54 → 200, no new login | ✅ |
| Server latency | — | 2–22 ms per request | ✅ |

## Findings (three fixes on our side, none in the server's checks)

1. **`invalid_scope: offline_access`.** Claude Code always adds `offline_access`. The realm import had replaced Keycloak's built-in scopes, so the scope did not exist. Fix: `offline_access` scope and role in the realm, offline sessions capped at 1 day idle and 7 days maximum, refresh tokens still rotated.
2. **Keycloak 26.8 loses the `resource` audience when refreshing an offline token.** The first access token had `aud = http://127.0.0.1:8014/mcp`; after an offline refresh it was the client id `legado-mcp`, and the server answered 401 (`InvalidAudienceError`) on every request. Claude Code was not at fault: the probe showed it gets the right audience on the first token whether `resource` goes in the authorization request only or in both. Removing the user's `offline_access` role does not help (Keycloak answers `not_allowed`). Fix: the agent client's audience mapper now emits the canonical URI instead of the client id.
   - Kept: the server still accepts only its own URI as audience (`test_auth.py`), and a `resource` naming another server is still `invalid_target`.
   - Given up: a token requested **without** `resource` is now also bound to this server. With a single resource server in the realm that is the right target; a second resource server would need its own client or mapper.
   - `test_offline_access_para_clientes_mcp` covers it, including a refresh without `resource`.
3. **The server's trace did not say why it answered 401.** Diagnosing "missing token" vs. "wrong password" vs. "wrong audience" took several rounds. The trace now records `motivo_auth` (`sin_token`, `token_invalido: <PyJWT error>`, `faltan: <scopes>`). The client still only sees `invalid_token`, so the reason does not help anyone forge tokens.

Also observed: the authorization request uses `prompt=consent` and the SDK warns that the stored credential has no `issuer` stamp (SEP-2352). Neither affected the flow.
