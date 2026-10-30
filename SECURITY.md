# Security policy

This repository is a research and teaching lab. It contains no production systems, and all data is synthetic.

## Reporting a vulnerability

Please report security issues privately through GitHub's **Report a vulnerability** button (the *Security* tab, then *Advisories*). Do not open a public issue. Include the file or workflow involved, the steps to reproduce, and the impact you expect. You will get an acknowledgement within 5 business days.

## What is in scope

- Code that could let a model or a user write to the database, read data outside its role or tenant, or follow injected instructions. These cases are tested as hard requirements; see `semana-13/resultados/seguridad.md` and `semana-14/seguridad/amenazas.md`.
- GitHub Actions workflows (`.github/workflows/`), including secret handling and OIDC federation.
- The MCP server and its OAuth resource-server logic (`semana-14/`).

## Credentials

- No credentials are stored in the repository.
- API keys exist only as GitHub Actions secrets, and only the steps that call a model can see them.
- Cloud access in CI uses OIDC federation with no long-lived keys. The trust policy uses GitHub's immutable subject (numeric owner and repository IDs) and a dedicated GitHub environment.
- Every cloud resource created for the experiments was deleted after the measurements (`semana-12/README.md`).
