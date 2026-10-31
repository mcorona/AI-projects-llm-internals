# Activity 4: authorization server (local Keycloak)

Files: [`auth/docker-compose.yml`](../auth/docker-compose.yml), [`auth/realm/legacybridge-realm.json`](../auth/realm/legacybridge-realm.json), [`auth/arrancar.sh`](../auth/arrancar.sh), [`auth/pkce.py`](../auth/pkce.py). Tests: [`tests/test_keycloak.py`](../tests/test_keycloak.py). Local only, with no API calls and no cloud resources: $0.

```bash
cd semana-14/auth
./arrancar.sh            # first run: generates .secretos.env (chmod 600, ignored by Git), starts Keycloak, imports the realm
./arrancar.sh            # idempotent: no duplicates; sets the same passwords again
./arrancar.sh --detener  # stop (keeps data)    ./arrancar.sh --borrar   # stop and delete the volume (re-imports the realm)
cd .. && python -m pytest -q tests/test_keycloak.py
```

## Configuration

| Element | Value |
|---|---|
| Image | `quay.io/keycloak/keycloak:26.8.1` (released 2026-10-13), `start-dev`, published on `127.0.0.1:8180` only (port 8080 inside the container; 8080 on the host was already taken on the dev Mac) |
| Feature | `--features=resource-indicators` (RFC 8707, experimental in 26.8) |
| Issuer | `http://127.0.0.1:8180/realms/legacybridge`, fixed with `--hostname` |
| Realm | `legacybridge`. Self-registration and password reset are off, brute-force protection is on, access tokens last 300 s, refresh tokens rotate (`revokeRefreshToken`), signatures use RS256 |
| Resource server | `legado-mcp`, bearer-only (it starts no flows) with `resource_url = http://127.0.0.1:8014/mcp` |
| MCP client | `legacybridge-agente`, public. Authorization code only with **PKCE S256 required**. Redirects go to loopback `http://127.0.0.1/callback` and `http://localhost/callback` on any port (RFC 8252). No password grant, no client credentials, no implicit flow, `fullScopeAllowed: false` |
| Audience | An Audience mapper on the client adds the canonical URI `http://127.0.0.1:8014/mcp` (until activity 7 it added the client id `legado-mcp`; changed because Keycloak loses the `resource` audience when refreshing offline tokens, see [`claude_code.md`](claude_code.md)). With `resource`, Keycloak uses the `resource_url` value. An unknown resource gets `invalid_target` |
| Scopes (optional client scopes) | `legado:leer`, `legado:ventas`, `legado:proveedores`, `legado:compras:proponer` |
| Assignment by profile | Each scope is tied to a realm role (`scopeMappings`), and Keycloak only grants it if the user has that role |
| Secrets | None in Git. `arrancar.sh` generates the bootstrap admin password and the 3 user passwords (24 random characters) into `.secretos.env` with `chmod 600`, and sets the user passwords with `kcadm` |

| User | Roles | Scopes it receives (when it asks for all four) |
|---|---|---|
| `analista` | lector, ventas, proveedores, compras | `legado:leer legado:ventas legado:proveedores legado:compras:proponer` |
| `almacenista` | lector | `legado:leer` |
| `vendedor` | lector, ventas | `legado:leer legado:ventas` |

## Verification

The docker-compose file is validated with `docker compose config`. The realm, the script and the tests were run on the same Keycloak 26.8.1 (official distribution, Temurin JDK 21), started with the same flags as the compose file, in `KC_MODO=externo` mode:

| Check | Result |
|---|---|
| First run: fresh secrets, realm import, passwords set, `resource_url` confirmed | ✓ |
| Second run (idempotency): no re-import (`IGNORE_EXISTING`, a single "imported"), same 3 users, same 4 scopes | ✓ |
| `.secretos.env` permissions | `600` |
| `tests/test_keycloak.py` | **18/18** (VM) and **18/18 against Docker on the dev Mac** |
| Full `semana-14` suite without a database | 69 passed, 16 skipped |

What the 18 tests cover:
- **Discovery:** the exact issuer, `S256`, `authorization_response_iss_parameter_supported: true` (RFC 9207), the 4 scopes and the JWKS.
- **Token per profile** (3 users): exact scopes, `aud` equal to the MCP URI, `iss`, `azp`, `sub`, and a lifetime of 300 s.
- **Signature:** RS256, verified with PyJWT against the JWKS (`audience` and `issuer` exact). A different audience is rejected. This is the activity 5 verifier.
- **Without `resource`:** originally the audience was `legado-mcp`, which the MCP server rejects (A06, A07). Since activity 7 the mapper always emits the canonical URI, because the realm has a single resource server; a different `resource` is still `invalid_target`, and the server still rejects any other audience.
- **Unknown `resource`:** `invalid_target` at authorization, and also when the resource changes between authorization and code exchange.
- **PKCE:** required, and `plain` is not accepted. A wrong verifier gets `invalid_grant`. The code works only once.
- **Redirects:** only to registered loopback addresses, on any port. `https://evil.example`, another path and a LAN IP are rejected.
- **Other grants:** the password and client-credentials grants are disabled. `legado-mcp` cannot request tokens or authorize users.
- **Refresh:** keeps the audience and the scopes, and the previous refresh token stops working (rotation).

## Findings

1. **A realm import replaces Keycloak's built-in client scopes.** Because the realm declares its own `clientScopes`, the default `basic` scope did not exist and the access token arrived without `sub` (3 tests failed). The realm now declares `basic` with the `sub` mapper. If you change the realm after it has been imported, use `./arrancar.sh --borrar` so the change takes effect.
2. **Keycloak's cookies are `Secure`.** Python's `CookieJar` does not send them over `http://127.0.0.1`, while browsers do, because they treat loopback as a secure context. The lab client (`pkce.py`) applies the same rule as a browser, for loopback only.
3. **Scopes are assigned per user through role scope mappings.** With `fullScopeAllowed: false` and each scope tied to a role, `almacenista` asks for all four scopes and receives only `legado:leer`. The MCP server therefore gets least privilege directly from the token. In activity 5 it still enforces it on its own side (tool list, database role per scope, `art_prv`).
4. **RFC 8707 in Keycloak:** it looks for the `resource` value among the audiences produced by the mappers, through the `resource_url` client attribute, and leaves only that one. Without the feature, plan B (a custom Audience mapper) would also give `aud` equal to the URI, but it would not reject an unknown resource.
5. **Docker on the dev Mac: two issues the VM did not show.**
   - Port 8080 on the host was taken by another local process, so Keycloak is published on **8180**. Inside the container it still listens on 8080.
   - The named volume was mounted on `/opt/keycloak/data/h2`, a directory that does not exist in the image. Docker created it owned by `root`, Keycloak (uid 1000) could not open the H2 database, and the container stayed in `Restarting`. The volume now mounts on `/opt/keycloak/data`, which takes its owner from the image. After `./arrancar.sh --borrar`, the first run imported the realm, the second confirmed idempotency, and the tests passed 18/18.
