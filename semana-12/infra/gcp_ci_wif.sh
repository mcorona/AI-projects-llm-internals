#!/usr/bin/env bash
# Semana 12, actividad 9 (Google Cloud, lo corre el dueño): Workload Identity Federation para GitHub Actions, sin llaves.
# Pool semana12-github con proveedor OIDC de GitHub limitado a este repo; cuenta de servicio semana12-ci (Discovery Engine
# viewer: buscar y rankear, sin crear ni borrar) que solo puede usar el sujeto repo:<repo>:environment:nube-semana12.
set -euo pipefail
cd "$(dirname "$0")"; source config.sh
SUJETO=$(gh_sujeto); P=$GCP_PROYECTO; NUM=$(gcloud projects describe $P --format='value(projectNumber)')
gcloud services enable iamcredentials.googleapis.com sts.googleapis.com --project=$P
gcloud iam service-accounts describe $GCP_SA_CI_EMAIL --project=$P >/dev/null 2>&1 || \
  gcloud iam service-accounts create $GCP_SA_CI --project=$P --display-name="Semana 12: CI manual (solo consulta)"
for r in roles/discoveryengine.viewer roles/serviceusage.serviceUsageConsumer; do
  gcloud projects add-iam-policy-binding $P --member=serviceAccount:$GCP_SA_CI_EMAIL --role=$r --condition=None >/dev/null
done
gcloud iam workload-identity-pools describe $GCP_POOL --location=global --project=$P >/dev/null 2>&1 || \
  gcloud iam workload-identity-pools create $GCP_POOL --location=global --project=$P --display-name="Semana 12 GitHub"
gcloud iam workload-identity-pools providers describe github --workload-identity-pool=$GCP_POOL --location=global --project=$P >/dev/null 2>&1 || \
  gcloud iam workload-identity-pools providers create-oidc github --workload-identity-pool=$GCP_POOL --location=global --project=$P \
    --issuer-uri=https://token.actions.githubusercontent.com \
    --attribute-mapping="google.subject=assertion.sub,attribute.repository=assertion.repository" \
    --attribute-condition="assertion.repository == '$GH_REPO'"
BASE=principal://iam.googleapis.com/projects/$NUM/locations/global/workloadIdentityPools/$GCP_POOL/subject
gcloud iam service-accounts add-iam-policy-binding $GCP_SA_CI_EMAIL --project=$P --role=roles/iam.workloadIdentityUser \
  --member="$BASE/$SUJETO" >/dev/null
# Quita el enlace con el formato de sujeto por nombre si quedó de una corrida anterior y ya no aplica
[ "$SUJETO" != "repo:$GH_REPO:environment:$GH_ENTORNO" ] && gcloud iam service-accounts remove-iam-policy-binding $GCP_SA_CI_EMAIL \
  --project=$P --role=roles/iam.workloadIdentityUser --member="$BASE/repo:$GH_REPO:environment:$GH_ENTORNO" >/dev/null 2>&1 || true
echo "sujeto aceptado: $SUJETO"
echo "proveedor: projects/$NUM/locations/global/workloadIdentityPools/$GCP_POOL/providers/github"
echo "cuenta de servicio: $GCP_SA_CI_EMAIL (llaves de usuario: $(gcloud iam service-accounts keys list --iam-account=$GCP_SA_CI_EMAIL --managed-by=user --format='value(name)' | wc -l | tr -d ' '))"
