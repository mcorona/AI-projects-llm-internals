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
| Impersonation | `gcloud auth print-access-token --impersonate-service-account=semana12-operador@...` returns a token |
| Required checks from week 11 | Skipped on this PR (it does not touch `semana-11/**`), and the PR is not blocked |
| `inventario.sh` | Only roles, a service account and budgets, none of which bills. No knowledge base, vector bucket, S3 or GCS bucket, data store or app |
| `aws_borrar.sh` / `gcp_borrar.sh` (simulation) | Each lists exactly the resources created |
| `revisar_secretos.sh` | No credentials in the repo |

Cost of activity 1: $0. Budgets, IAM roles, service accounts and price catalog queries are free.

## 2. Document base and permissions, frozen

[`ingesta/construir_paquete.py`](ingesta/construir_paquete.py) builds [`ingesta/paquete/`](ingesta/paquete/), which is uploaded as is to S3 and to GCS. The build is deterministic: two runs give the same manifest. It makes no API calls and costs nothing.

### Contents

The base is the own pipeline's index (week 10, activity 7) plus the week 9 `beta` tenant, which activity 6 needs for cross-tenant leak tests.

| Tenant | Documents | Original formats | Chunks (fixed 400/80) |
|---|---|---|---|
| `alfa` | 30 | 24 Markdown, 2 PDF with tables, 2 JPG scans, 2 PNG images | 68, the same as `semana10.chunks` |
| `beta` | 10 | Markdown (same names as in `alfa`, with a different figure in the gold passage) | 33 |

The package has one folder per ingestion mode:

| Folder | Mode | What it holds |
|---|---|---|
| `administrado/<tenant>/` | Managed | The original files. Each service parses, chunks and embeds them with its native options |
| `controlado/textos/<tenant>/` | Controlled | The text the own pipeline indexes: pdfplumber for PDF, Haiku transcription for scans, Haiku description for images, Markdown as is |
| `controlado/chunks/<tenant>/` | Controlled | The own pipeline's 101 chunks, one per file, to ingest without re-chunking (Bedrock chunking strategy `NONE`). This isolates index and ranking quality |

### Permissions in each service's format

Every document and chunk carries the same fields:

| Field | Type | Content |
|---|---|---|
| `tenant_id` | text | `alfa` or `beta` |
| `roles` | list of text | The roles of weeks 9 and 10 (`permisos.json`, `permisos_semana10.json`): almacen, calidad, compras, finanzas, operaciones, ventas |
| `source` | text | Document name without extension, the key the week 11 metrics use |
| `doc_id` | text | `<tenant>__<source>`, plus `__NNN` for chunks |
| `tipo` | text | `texto`, `pdf`, `jpg` or `png` |
| `chunk` | number | Chunk index (chunks only) |

How each service receives them:
- **Bedrock Knowledge Bases:** a `<file>.metadata.json` next to each file in S3, with `{"metadataAttributes": {...}}`. Filters: `equals` on `tenant_id`, `listContains` / `in` on `roles`.
- **Vertex AI Search:** one JSONL per mode (`vertex_administrado.jsonl`, `vertex_controlado_textos.jsonl`, `vertex_controlado_chunks.jsonl`). Each line has `id`, `structData` (the same fields) and `content.uri` in `gs://semana12-docs-ejemplo1-9xub/...`. `tenant_id` and `roles` are made filterable in the data store schema (activity 5). Filter: `tenant_id: ANY("alfa") AND roles: ANY("ventas")`.

### Validations (all pass; recorded in `paquete/manifiesto.json`)

| Check | Result |
|---|---|
| Documents per tenant | 30 `alfa`, 10 `beta` |
| `alfa` chunks equal to the own index | 68 |
| Documents without roles | 0 |
| Original files identical to their sources (sha256) | 40/40 |
| Week 11 gold passages intact in a chunk of their document | 136/136 |
| Multitenant passages (`alfa` and `beta`) intact | 40/40 |
| Gold sets unchanged against `main` (week 11 `eval_rag_{es,en}`, week 9 `multitenant_{es,en}`) | yes; sha256 recorded |
| Vertex document ids unique and ≤ 63 characters | yes (max 38) |

The `infra-semana-12` CI check rebuilds the package on every PR that touches `semana-12/**`. It fails if the package changes or if a gold set differs from `main`.

**To check in activities 4 and 5:** which original formats each service ingests in managed mode. The default Bedrock parser does not read images (that needs Bedrock Data Automation or a model parser), and Vertex AI Search may not accept JPG or PNG as unstructured documents. The controlled mode covers those documents with their extracted text either way.

## 3. Baseline: own pipeline with the week 11 suites

[`evaluacion/suites.py`](evaluacion/suites.py) is the evaluator for the whole week. Each option is a retrieval backend; the gold set, the common generator (Haiku 5.5 `medium`, `solo_documentos`), the judge (Haiku 5.5 `low`) and the metrics stay the same. Results: [`resultados/linea_base.md`](resultados/linea_base.md); the reference for every comparison is `resultados/propio_resumen.json`.

| Lang | recall@1 | recall@5 | MRR | nDCG@10 | AP@5 | doc_recall@5 | Correctness | faithfulness | answer relevancy | Correct abstention |
|---|---|---|---|---|---|---|---|---|---|---|
| ES | 0.892 | 1.000 | 0.949 | 0.962 | 0.949 | 1.000 | 1.000 | 0.849 | 0.879 | 10/10 |
| EN | 0.885 | 1.000 | 0.954 | 0.965 | 0.950 | 1.000 | 1.000 | 0.830 | 0.866 | 10/10 |

- 0 failures out of 150.
- Per query: $0.00049 to retrieve (p50 2.3 s) and $0.00021 to generate (p50 1.7 s).
- Cost of the activity: ≈ $0.25.

## 4. Bedrock Knowledge Bases

Four knowledge bases on S3 Vectors with Cohere Embed Multilingual v3, created and loaded by [`infra/aws_kb_crear.sh`](infra/aws_kb_crear.sh) and measured with the common evaluator. Results: [`resultados/bedrock.md`](resultados/bedrock.md).

| Option (ES) | recall@5 | MRR | doc_recall@5 | Correctness | faithfulness |
|---|---|---|---|---|---|
| Own pipeline (baseline) | 1.000 | 0.949 | 1.000 | 1.000 | 0.849 |
| `adm-pred`: originals, default chunking and parser | 0.823 | 0.755 | 0.831 | 0.815 | 0.815 |
| `adm-fijo`: fixed 100 tokens / 20% | 0.815 | 0.728 | 0.846 | 0.831 | 0.888 |
| `adm-fijo-bda`: BDA multimodal parser | 0.739 | 0.659 | 0.985 | 0.708 | 0.761 |
| `ctl-chunks`: own chunks, no re-chunking | 1.000 | 0.863 | 1.000 | 0.985 | 0.881 |
| `adm-fijo-bda` + RetrieveAndGenerate (Haiku 4.5) | 0.739 | 0.659 | 0.985 | **0.969** | 0.739 |
| `ctl-chunks` + RetrieveAndGenerate (Haiku 4.5) | 1.000 | 0.863 | 1.000 | 0.985 | **0.947** |

- **Ingestion:**
  - With the own chunks, Bedrock matches the own pipeline on coverage. The remaining gap is reranking.
  - The default parser loses every scan and image.
  - BDA multimodal returns PDFs and images as images: only RetrieveAndGenerate, which passes them to Claude, uses them.
- **Leakage:** 0 chunks from another tenant in every run.
- **Cost and latency:**
  - Bedrock retrieval: ≈ $0.00006 per query, p50 0.5 s.
  - RetrieveAndGenerate: ≈ $0.001 to $0.0017 per answer (Haiku 4.5, estimated), p95 9 to 10 s.
- Cost of the activity: ≈ $2.2.

## 5. Second cloud: Vertex AI Search

Two data stores in project `ejemplo1-9xub`, created by [`infra/vertex_crear.py`](infra/vertex_crear.py) with the operator service account (impersonation, no keys) and measured with the common evaluator. Results: [`resultados/vertex.md`](resultados/vertex.md).

- **Managed:** `vx-adm`, originals parsed by the layout parser with default 500-token chunking. Markdown becomes HTML and images become PDF, because the service does not import them as they are.
- **Controlled:** `vx-ctl`, the own 101 chunks pushed as documents.
- **Filters:** `tenant_id` and `roles` are filterable in the schema and applied inside the query.
- **Search modes:** hybrid (default), vector (`semantic_similarity_score` ranking) and the semantic ranker (Ranking API).

| Option (ES / EN) | recall@5 | MRR | doc_recall@5 | Correctness |
|---|---|---|---|---|
| Own pipeline (baseline) | 1.000 / 1.000 | 0.949 / 0.954 | 1.000 / 1.000 | 1.000 / 1.000 |
| `vx-adm` hybrid / vector / semantic | 0.83 / 0.81 / 0.83 | 0.82 / 0.79 / 0.84 | 1.00 / 0.98 / 1.00 | 0.92 / 0.91 / 0.92 |
| `vx-ctl` hybrid | 1.000 / 0.962 | 0.949 / 0.860 | 1.000 / 0.985 | 1.000 / 0.969 |
| `vx-ctl` vector | 1.000 / 1.000 | 0.897 / 0.881 | 1.000 / 1.000 | 1.000 / 0.985 |
| `vx-ctl` semantic ranker | **1.000 / 1.000** | **0.977 / 0.962** | 1.000 / 1.000 | 0.985 / 0.985 |

- **Ranking:**
  - With the same chunks, Google's semantic ranker ranks better than the own Haiku reranking: MRR 0.97 vs 0.95, 0.7 s instead of 2.3 s.
  - Hybrid search loses in English because of its keyword component.
- **Managed ingestion:** it reads PDFs and scans, but OCR alone cannot tie chart values to their labels, so the 5 image questions fail.
- **Leakage:** 0 in every run. Correct abstention: 10/10 everywhere.
- **Cost:** queries are within the free tier; the semantic ranker costs $0.001 per query. Cost of the activity: ≈ $2.

## 6. Security in the managed services

[`evaluacion/seguridad.py`](evaluacion/seguridad.py) runs the week 10 leakage tests against the managed services. Results: [`resultados/seguridad.md`](resultados/seguridad.md).

- **Tests:** 56 by role (an `alfa` user with one role that cannot see the gold document) and 40 across tenants (`alfa` and `beta` users).
- **Systems:** 4 Bedrock knowledge bases, RetrieveAndGenerate, and 2 Vertex data stores.

| | Leakage with filter | Same queries without filter (control) |
|---|---|---|
| Bedrock (4 KB + RetrieveAndGenerate) | **0** in 480 queries | 1,426 unauthorized chunks in 96 queries (`ctl-chunks`) |
| Vertex AI Search (2 data stores) | **0** in 192 queries | 1,470 unauthorized chunks in 96 queries (`vx-ctl`) |

- Tenant and roles are checked against the real file path and the frozen manifest, not the service's metadata.
- **The filter is applied inside the query:** single-role users get exactly the number of chunks they are allowed to see, up to 20.
- **Neither service is ruled out.** Cost: ≈ $0.20.

## 7. Latency and cost

Same client and location (one Mac in Guadalajara), concurrency 1, 100 questions with the options in random order per question. Results: [`resultados/latencia_costo.md`](resultados/latencia_costo.md).

| Option | Full answer p50 / p95 (s) | Fixed USD per month | USD per query | Monthly USD at 10k / 100k queries | More expensive than own pipeline from |
|---|---|---|---|---|---|
| Own pipeline (hosted on RDS db.t4g.micro) | 3.89 / 6.07 | 13.98 | 0.000703 | 21.01 / 84.28 | — |
| Bedrock `Retrieve` + common generator | 2.58 / 4.09 | ≈ 0 | **0.000269** | **2.69 / 26.90** | never |
| Bedrock RetrieveAndGenerate (Haiku 4.5) | **1.50 / 2.21** | ≈ 0 | 0.001083 (est.) | 10.83 / 108.30 | ≈ 37,000 per month |
| Vertex + semantic ranker | 2.40 / 3.94 | ≈ 0 | 0.001213 + $0.004 past 10k per month | 12.13 / 481.30 | ≈ 12,000 per month |

- **One-time ingestion:** under $0.05 on Bedrock, and $0.40 on Vertex (layout parser on 40 pages).
- **Retrieval:** the own reranking adds 2.2 s. RetrieveAndGenerate is the fastest full answer, because it makes a single call inside AWS.
- **Cost of the activity:** ≈ $0.50.
