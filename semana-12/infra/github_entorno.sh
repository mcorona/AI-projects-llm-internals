#!/usr/bin/env bash
# Semana 12, actividad 9: entorno de GitHub nube-semana12, solo desplegable desde main, con las variables (no secretas)
# que usa el workflow manual para federarse con AWS y Google Cloud. Las llaves de Anthropic y OpenAI se guardan como
# secretos DEL ENTORNO: solo los ve un job que declara environment: nube-semana12, es decir, el workflow manual.
set -euo pipefail
cd "$(dirname "$0")"; source config.sh
NUM=$(gcloud projects describe $GCP_PROYECTO --format='value(projectNumber)')
gh api -X PUT repos/$GH_REPO/environments/$GH_ENTORNO --input - >/dev/null <<J
{"deployment_branch_policy":{"protected_branches":false,"custom_branch_policies":true}}
J
gh api repos/$GH_REPO/environments/$GH_ENTORNO/deployment-branch-policies --jq '.branch_policies[].name' | grep -qx main || \
  gh api -X POST repos/$GH_REPO/environments/$GH_ENTORNO/deployment-branch-policies -f name=main -f type=branch >/dev/null
gh variable set AWS_ROLE_ARN --env $GH_ENTORNO --repo $GH_REPO --body "arn:aws:iam::$CUENTA_AWS:role/$ROL_CI"
gh variable set GCP_WIF_PROVIDER --env $GH_ENTORNO --repo $GH_REPO --body "projects/$NUM/locations/global/workloadIdentityPools/$GCP_POOL/providers/github"
gh variable set GCP_SA --env $GH_ENTORNO --repo $GH_REPO --body "$GCP_SA_CI_EMAIL"
gh variable set GCP_PROYECTO --env $GH_ENTORNO --repo $GH_REPO --body "$GCP_PROYECTO"
[ -n "${ANTHROPIC_API_KEY:-}" ] && printf %s "$ANTHROPIC_API_KEY" | gh secret set ANTHROPIC_API_KEY --env $GH_ENTORNO --repo $GH_REPO
[ -n "${OPENAI_API_KEY:-}" ] && printf %s "$OPENAI_API_KEY" | gh secret set OPENAI_API_KEY --env $GH_ENTORNO --repo $GH_REPO
echo "entorno $GH_ENTORNO: solo main; variables:"; gh variable list --env $GH_ENTORNO --repo $GH_REPO
echo "secretos del entorno:"; gh secret list --env $GH_ENTORNO --repo $GH_REPO
