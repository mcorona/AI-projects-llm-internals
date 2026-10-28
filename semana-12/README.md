# Week 12: managed RAG (Bedrock Knowledge Bases and Vertex AI Search)

Status: in progress.

Goal: load the same document base into a managed RAG on AWS (Bedrock Knowledge Bases with S3 Vectors) and on Google Cloud (Vertex AI Search), and compare both with the own pipeline from weeks 8 to 10. The comparison covers quality, latency, cost and security, using the week 11 suites.

## 1. Accounts, permissions and cost control

### Choices

| Item | Choice | Verified on 2026-10-28 |
|---|---|---|
| AWS region | us-east-1 | Bedrock (124 models), Knowledge Bases, S3 Vectors (GA in 14 regions, including us-east-1), Titan Text Embeddings V2 and Cohere Embed Multilingual v3 |
| Claude on Bedrock | **Haiku 4.5** (`us.anthropic.claude-haiku-4-5-20251001-v1:0`) | Haiku 5.5 is in the region and its agreement is accepted, but the account's applied tokens-per-minute quota is 0 (default 10M). An increase is requested through AWS Support. Haiku 4.5 answers |
| Second cloud | Vertex AI Search (Discovery Engine API; now "Agent Search" in AI Applications), project `ejemplo1-9xub`, location `global` | Discovery Engine API answers (HTTP 200); 0 data stores |
| Common generator and judge | Haiku 5.5 through the Anthropic API, as in weeks 8 to 11 | |

The Claude model is used only in Bedrock's fully managed `RetrieveAndGenerate` mode. Retrieval quality is compared with the same Anthropic generator for every option.

### Permissions (least privilege)

**AWS** ([`infra/aws_crear.sh`](infra/aws_crear.sh), run once by the administrator):
- **`semana12-bedrock-kb`**, the Knowledge Base service role:
  - Trusted only by `bedrock.amazonaws.com` from this account's knowledge bases.
  - It can read the documents bucket, write and query the `semana12` vector bucket, and invoke only the two embedding models.
- **`semana12-operador`**, the role the week's scripts run as, through the local profile `semana12`:
  - It can manage knowledge bases and their data sources, ingestion and retrieval.
  - It can invoke only Titan V2, Cohere multilingual and Claude Haiku 4.5 / 5.5.
  - It has S3 access only to the `semana12-docs-*` bucket, and S3 Vectors access only to `semana12-vectores-*`.
  - It can pass only the KB role, and only to Bedrock.
  - The administrator user is not used for the week's work.

**Google Cloud** ([`infra/gcp_crear.sh`](infra/gcp_crear.sh)):
- **`semana12-operador@ejemplo1-9xub.iam.gserviceaccount.com`**, the service account the week's scripts use:
  - Its only project role is `roles/discoveryengine.editor`.
  - Access to the documents bucket is granted on the bucket itself, when it is created.
- **It has no key files:** the script checks that the account has 0 user-managed keys.
- **It is used by impersonation:** only the project owner holds `roles/iam.serviceAccountTokenCreator` on it. The week's scripts get credentials with `gcloud auth application-default login --impersonate-service-account=...`.

### Credentials outside the repo

| Credential | Where it lives |
|---|---|
| AWS | CLI session (`aws login`) and the `semana12` profile in `~/.aws/config`, which assumes the operator role. No access keys |
| Google Cloud | gcloud session and ADC in `~/.config/gcloud`, impersonating the service account. No key files |
| Anthropic | `ANTHROPIC_API_KEY` in the environment (`.env` is ignored by Git) |

- `.gitignore` also ignores `*.pem`, `*credentials*.json`, `*-key.json` and `*service-account*.json`.
- [`infra/revisar_secretos.sh`](infra/revisar_secretos.sh) scans every versioned or pending file for AWS, Google, Anthropic and OpenAI keys and for private keys.
- **CI holds no cloud credentials.** The `infra-semana-12` workflow runs on every PR that touches `semana-12/**`. It checks the syntax of the infra scripts and runs the secret scan. Cloud evaluations run locally (activity 9 defines their manual workflow).

### Cost control

- **Budgets:**
  - AWS: `semana12`, $10 per month, with alerts at 50, 90 and 100% actual and 100% forecasted.
  - Google Cloud: `semana12`, 200 MXN (about $10 USD), scoped to the project, with the same thresholds.
- **Naming and tags:** every resource uses the `semana12` prefix and the tag `proyecto=semana12`.
- **Deletion:**
  - [`infra/aws_borrar.sh`](infra/aws_borrar.sh) and [`infra/gcp_borrar.sh`](infra/gcp_borrar.sh) delete in dependency order. On AWS: knowledge bases and data sources, vector indexes and buckets, S3 buckets, then roles. On Google Cloud: apps, data stores, buckets, then the service account.
  - Both **simulate by default** and delete only with `--confirmar`. Budgets are kept until the bill is checked (`--presupuesto`).
- [`infra/inventario.sh`](infra/inventario.sh) lists what still exists in each cloud.

Verified prices and the estimate for the week are in [`resultados/costos_fijos.md`](resultados/costos_fijos.md):
- The fixed monthly cost of both managed options is about $0 for this corpus.
- The week is estimated at $3 to $4.

### Verification (2026-10-28)

| Check | Result |
|---|---|
| `aws_crear.sh` | Budget, both roles and the profile created. `aws sts get-caller-identity --profile semana12` returns `assumed-role/semana12-operador` |
| `gcp_crear.sh` | Budget (200 MXN) and service account created; 0 user-managed keys |
| `inventario.sh` | Only roles, a service account and budgets, none of which bills. No knowledge base, vector bucket, S3 or GCS bucket, data store or app |
| `aws_borrar.sh` / `gcp_borrar.sh` (simulation) | Each lists exactly the resources created |
| `revisar_secretos.sh` | No credentials in the repo |

Cost of activity 1: $0. Budgets, IAM roles, service accounts and price catalog queries are free.
