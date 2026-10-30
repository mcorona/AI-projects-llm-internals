# Activity 1: baseline (specification, SDK, authorization server)

Verified on 2026-10-30. Reproduce it with `python semana-14/linea_base/verificar_sdk.py`: no network, no database, no API, $0.

## Specification

| Item | Finding | Decision for the week |
|---|---|---|
| Current version | **2026-07-28**. `specification/latest` serves it, and it is the `LATEST_PROTOCOL_VERSION` of the SDK. | Implement 2026-07-28 |
| Transport | Streamable HTTP with no protocol-level sessions and no `initialize`: every POST carries its `_meta` (version, client, capabilities). The GET stream is gone (405); there is `subscriptions/listen` for notifications. | Stateless server, `json_response=True` |
| Mandatory headers | `MCP-Protocol-Version`, `Mcp-Method`, and `Mcp-Name` (for `tools/call`, `resources/read` and `prompts/get`). A mismatch with the body gets `400` and `-32020 HeaderMismatch`. | Per-tool authorization uses the body (A11) |
| HTTP security | `Origin` MUST be validated (403 if invalid); SHOULD bind to `127.0.0.1`; SHOULD authenticate every connection | A08 |
| Authorization | OAuth 2.1. The server is a resource server and MUST publish Protected Resource Metadata (RFC 9728). The client MUST send `resource` (RFC 8707), and the server MUST validate the audience and MUST NOT accept or forward other tokens. Invalid or expired tokens get 401; insufficient scope gets 403 (`insufficient_scope`, with `scope` and `resource_metadata`), followed by step-up. The token is not accepted in the query string. | A06, A07, A09 |
| Client registration | Priority: Client ID Metadata Documents (SHOULD), then pre-registration, then dynamic registration (deprecated). The client MUST validate `iss` (RFC 9207). | Pre-registered public client with PKCE (CIMD is out of scope) |
| Security best practices | Confused deputy (OAuth proxies), token passthrough, SSRF during discovery, state handle hijacking (it replaces session hijacking), mix-up, scope minimization | `seguridad/amenazas.md` |

## SDK `mcp` 2.3.0 (PyPI, 2026-10-02; already pinned in the repo since week 13)

24/24 checks pass, all of them on an in-memory server built with `MCPServer` and `streamable_http_app`:

| Capability | Result |
|---|---|
| Protocol 2026-07-28 (modern, no handshake); also supports 2024-11-05 through 2025-11-25 | ✓ |
| Streamable HTTP with no `mcp-session-id`; `tools/list` and `tools/call` | ✓ |
| `outputSchema` and `structuredContent` | ✓ only with a typed return (Pydantic model); with a bare `dict` the SDK publishes no schema |
| Annotations (`readOnlyHint` and `destructiveHint`), resource templates (`legado://esquema/{vista}`), `resources/read`, `prompts/get` | ✓ |
| `cacheScope` and `ttlMs` in results | ✓ (`tools/list` returns `cacheScope: private`) |
| Resource server: `TokenVerifier`, `AuthSettings(resource_server_url, validate_token_resource, required_scopes)` | ✓ |
| RFC 9728: `/.well-known/oauth-protected-resource/mcp` with `resource`, `authorization_servers` and `scopes_supported` | ✓ |
| 401 with `WWW-Authenticate: resource_metadata=…` when there is no token, or when the token is unknown, expired, for another audience, or has no `resource` | ✓ |
| 403 `insufficient_scope` | ✓ |
| `?access_token=` ignored (401) | ✓ |
| `Origin` hostile → 403 (DNS rebinding protection on by default) | ✓ |
| `Mcp-Method` or `Mcp-Name` different from the body → 400 `-32020` | ✓ |

**Gaps (built during the week):**
1. **JWT validation:** `TokenVerifier` is only a protocol, so JWKS, `iss`, `aud`, `exp` and the fixed algorithm are built with PyJWT (activity 5).
2. **Per-tool scopes:** `required_scopes` is global, so per-tool scopes and filtering of `tools/list` and `resources/list` are built in the server (activity 5).
3. **Scope in challenges:** the 401 and 403 challenges do not include `scope=` (a SHOULD in the specification). It is added in activity 5.
4. **Client defenses:** the allowlist, hash pinning and server prefix are not in the client SDK. They are built in activity 6.

## Authorization server (Keycloak)

Source: Keycloak's [MCP integration guide](https://www.keycloak.org/securing-apps/mcp-authz-server).

| Feature | Status | Decision |
|---|---|---|
| RFC 8707 `resource` | Experimental (`--features=resource-indicators`). Without it, Keycloak ignores `resource`. | Turn the feature on. **Plan B:** an *Audience* mapper per client scope with the MCP URI. Either way the server validates `aud`. |
| RFC 9207 `iss` | Supported | The client validates it (A12) |
| CIMD | Experimental (`--features=cimd`) | Out of scope |
| Dynamic registration | Supported | Not used (deprecated in the specification) |
| PKCE | Public clients with PKCE | Pre-registered public client, `S256` |

## Impact on the plan

- **Protocol:** the plan offered a choice; the decision is 2026-07-28, the current version, which the SDK fully supports.
- **Activity 2:** typed returns (Pydantic) are needed to publish `outputSchema`. The manifest hashes `tools/list` as served.
- **Activity 5:** all four SDK gaps above. The 403 for a per-tool scope is decided by the body (`params.name`), not by `Mcp-Name`.
- **Activity 4:** Keycloak 26.x with `--features=resource-indicators` and the Audience mapper as plan B. The exact version is pinned in activity 4.

Threat model: [`../seguridad/amenazas.md`](../seguridad/amenazas.md). It has 13 threats (the 10 from the plan plus 3 from the specification), each with its mitigation, its test and the activity that implements it.
