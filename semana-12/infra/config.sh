# Semana 12: nombres y parámetros compartidos por los scripts de infra. Sin secretos: las credenciales vienen de la
# sesión de cada CLI (aws login / perfil `semana12`; gcloud con ADC por impersonación). Se carga con `source`.
REGION=us-east-1
PREFIJO=semana12
ETIQUETA_CLAVE=proyecto
ETIQUETA_VALOR=semana12
PRESUPUESTO_USD=10
# Correo para las alertas de presupuesto: se toma del entorno para no versionarlo.
ALERTA_CORREO=${ALERTA_CORREO:-$(git config user.email 2>/dev/null)}

# AWS
CUENTA_AWS=${CUENTA_AWS:-$(aws sts get-caller-identity --query Account --output text 2>/dev/null)}
S3_DOCS=${PREFIJO}-docs-${CUENTA_AWS}
S3_VECTORES=${PREFIJO}-vectores-${CUENTA_AWS}
S3_MULTIMODAL=${PREFIJO}-multimodal-${CUENTA_AWS}   # almacenamiento suplementario de BDA multimodal (raíz de bucket)
ROL_KB=${PREFIJO}-bedrock-kb
ROL_OPERADOR=${PREFIJO}-operador
PERFIL_AWS=${PREFIJO}
MODELOS_EMB=("amazon.titan-embed-text-v2:0" "cohere.embed-multilingual-v3")
PERFILES_CLAUDE=("us.anthropic.claude-haiku-4-5-20251001-v1:0" "us.anthropic.claude-haiku-5-5")
MODELOS_CLAUDE=("anthropic.claude-haiku-4-5-20251001-v1:0" "anthropic.claude-haiku-5-5")

# Google Cloud
GCP_PROYECTO=${GCP_PROYECTO:-ejemplo1-9xub}
GCP_UBICACION=global
GCS_DOCS=${PREFIJO}-docs-${GCP_PROYECTO}
GCP_SA=${PREFIJO}-operador
GCP_SA_EMAIL=${GCP_SA}@${GCP_PROYECTO}.iam.gserviceaccount.com

# CI (actividad 9): el workflow manual se autentica con OIDC; solo jobs del entorno de GitHub nube-semana12 en este repo.
GH_REPO=mcorona/genai-engineering-lab
GH_ENTORNO=nube-semana12
ROL_CI=${PREFIJO}-ci
GCP_SA_CI=${PREFIJO}-ci
GCP_SA_CI_EMAIL=${GCP_SA_CI}@${GCP_PROYECTO}.iam.gserviceaccount.com
GCP_POOL=${PREFIJO}-github
# Sujeto (sub) del token OIDC que GitHub emite para el entorno. Si el repo usa sujeto inmutable (use_immutable_subject),
# el prefijo lleva los ids numéricos del dueño y del repo (repo:dueño@id/repo@id); se lee de la API para no fijarlo a mano.
gh_sujeto() {
  local p; p=$(gh api repos/$GH_REPO/actions/oidc/customization/sub --jq 'if .use_immutable_subject then .sub_claim_prefix else "" end')
  echo "${p:-repo:$GH_REPO}:environment:$GH_ENTORNO"
}
