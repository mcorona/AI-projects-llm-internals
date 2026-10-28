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
