#!/usr/bin/env bash
# Semana 12, actividad 1 (AWS): presupuesto con alertas, rol de servicio de la Knowledge Base y rol operador con
# permisos mínimos, más el perfil `semana12` que asume ese rol. Idempotente. Lo corre un administrador (manuel-admin).
# No crea recursos facturables (buckets, vector buckets, KB): eso va en las actividades 2 y 4.
set -euo pipefail
cd "$(dirname "$0")"; source config.sh
export AWS_PAGER=""
[ -n "$CUENTA_AWS" ] || { echo "Sin sesión de AWS (aws login)"; exit 1; }
[ -n "$ALERTA_CORREO" ] || { echo "Define ALERTA_CORREO=<correo> para las alertas del presupuesto"; exit 1; }
YO=$(aws sts get-caller-identity --query Arn --output text)
echo "cuenta $CUENTA_AWS, región $REGION, como $YO"
TMP=$(mktemp -d)

# 1. Presupuesto mensual de la cuenta (los costos por etiqueta requieren activar la etiqueta de asignación y tardan 24 h).
if aws budgets describe-budget --account-id "$CUENTA_AWS" --budget-name "$PREFIJO" >/dev/null 2>&1; then
  echo "presupuesto $PREFIJO: ya existe"
else
  cat > $TMP/presupuesto.json <<J
{"BudgetName":"$PREFIJO","BudgetLimit":{"Amount":"$PRESUPUESTO_USD","Unit":"USD"},"TimeUnit":"MONTHLY","BudgetType":"COST"}
J
  python3 - "$ALERTA_CORREO" > $TMP/avisos.json <<'P'
import json, sys
s = [{"SubscriptionType": "EMAIL", "Address": sys.argv[1]}]
n = [{"Notification": {"NotificationType": t, "ComparisonOperator": "GREATER_THAN", "Threshold": u, "ThresholdType": "PERCENTAGE"}, "Subscribers": s}
     for t, u in (("ACTUAL", 50), ("ACTUAL", 90), ("ACTUAL", 100), ("FORECASTED", 100))]
print(json.dumps(n))
P
  aws budgets create-budget --account-id "$CUENTA_AWS" --budget file://$TMP/presupuesto.json \
    --notifications-with-subscribers file://$TMP/avisos.json
  echo "presupuesto $PREFIJO: creado (\$$PRESUPUESTO_USD al mes; alertas 50/90/100 % real y 100 % pronosticado)"
fi

etiquetas="Key=$ETIQUETA_CLAVE,Value=$ETIQUETA_VALOR"
crear_rol() {  # nombre, archivo de confianza
  if aws iam get-role --role-name "$1" >/dev/null 2>&1; then
    aws iam update-assume-role-policy --role-name "$1" --policy-document file://$2; echo "rol $1: confianza actualizada"
  else
    aws iam create-role --role-name "$1" --assume-role-policy-document file://$2 --tags $etiquetas --max-session-duration 14400 >/dev/null
    echo "rol $1: creado"
  fi
}
lista() { local p=$1; shift; local out=""; for x in "$@"; do out+="\"${p}${x}\","; done; echo "${out%,}"; }

# 2. Rol de servicio de la Knowledge Base: lee el bucket de documentos, escribe y consulta el vector bucket, embebe.
cat > $TMP/confianza_kb.json <<J
{"Version":"2012-10-17","Statement":[{"Effect":"Allow","Principal":{"Service":"bedrock.amazonaws.com"},"Action":"sts:AssumeRole",
 "Condition":{"StringEquals":{"aws:SourceAccount":"$CUENTA_AWS"},"ArnLike":{"aws:SourceArn":"arn:aws:bedrock:$REGION:$CUENTA_AWS:knowledge-base/*"}}}]}
J
cat > $TMP/permisos_kb.json <<J
{"Version":"2012-10-17","Statement":[
 {"Sid":"LeerDocumentos","Effect":"Allow","Action":["s3:GetObject","s3:ListBucket"],"Resource":["arn:aws:s3:::$S3_DOCS","arn:aws:s3:::$S3_DOCS/*"],
  "Condition":{"StringEquals":{"aws:ResourceAccount":"$CUENTA_AWS"}}},
 {"Sid":"VectorBucket","Effect":"Allow","Action":["s3vectors:PutVectors","s3vectors:GetVectors","s3vectors:DeleteVectors","s3vectors:QueryVectors","s3vectors:ListVectors","s3vectors:GetIndex"],
  "Resource":["arn:aws:s3vectors:$REGION:$CUENTA_AWS:bucket/$S3_VECTORES","arn:aws:s3vectors:$REGION:$CUENTA_AWS:bucket/$S3_VECTORES/index/*"]},
 {"Sid":"Embeddings","Effect":"Allow","Action":["bedrock:InvokeModel"],"Resource":[$(lista "arn:aws:bedrock:$REGION::foundation-model/" "${MODELOS_EMB[@]}")]},
 {"Sid":"ParserBDA","Effect":"Allow","Action":["bedrock:InvokeDataAutomationAsync"],"Resource":[
   "arn:aws:bedrock:$REGION:aws:data-automation-project/public-rag-default","arn:aws:bedrock:us-*:$CUENTA_AWS:data-automation-profile/*"]},
 {"Sid":"ParserBDAEstado","Effect":"Allow","Action":["bedrock:GetDataAutomationStatus"],"Resource":"arn:aws:bedrock:us-*:$CUENTA_AWS:data-automation-invocation/*"}]}
J
crear_rol "$ROL_KB" $TMP/confianza_kb.json
aws iam put-role-policy --role-name "$ROL_KB" --policy-name "${PREFIJO}-kb" --policy-document file://$TMP/permisos_kb.json

# 3. Rol operador: lo asume el usuario que corre la semana; solo los recursos con prefijo semana12 y los modelos usados.
cat > $TMP/confianza_op.json <<J
{"Version":"2012-10-17","Statement":[{"Effect":"Allow","Principal":{"AWS":"$YO"},"Action":"sts:AssumeRole"}]}
J
cat > $TMP/permisos_op.json <<J
{"Version":"2012-10-17","Statement":[
 {"Sid":"Lectura","Effect":"Allow","Action":["bedrock:ListFoundationModels","bedrock:GetFoundationModel","bedrock:ListInferenceProfiles","bedrock:GetInferenceProfile",
   "bedrock:ListKnowledgeBases","s3:ListAllMyBuckets","s3vectors:ListVectorBuckets","budgets:ViewBudget"],"Resource":"*"},
 {"Sid":"CrearKnowledgeBase","Effect":"Allow","Action":["bedrock:CreateKnowledgeBase"],"Resource":"*",
  "Condition":{"StringEquals":{"aws:RequestTag/$ETIQUETA_CLAVE":"$ETIQUETA_VALOR"}}},
 {"Sid":"KnowledgeBases","Effect":"Allow","Action":["bedrock:GetKnowledgeBase","bedrock:UpdateKnowledgeBase","bedrock:DeleteKnowledgeBase",
   "bedrock:CreateDataSource","bedrock:GetDataSource","bedrock:UpdateDataSource","bedrock:DeleteDataSource","bedrock:ListDataSources",
   "bedrock:StartIngestionJob","bedrock:GetIngestionJob","bedrock:ListIngestionJobs","bedrock:Retrieve","bedrock:TagResource","bedrock:ListTagsForResource"],
  "Resource":"arn:aws:bedrock:$REGION:$CUENTA_AWS:knowledge-base/*"},
 {"Sid":"RetrieveAndGenerate","Effect":"Allow","Action":["bedrock:RetrieveAndGenerate"],"Resource":"*"},
 {"Sid":"Modelos","Effect":"Allow","Action":["bedrock:InvokeModel","bedrock:InvokeModelWithResponseStream"],"Resource":[
   $(lista "arn:aws:bedrock:$REGION::foundation-model/" "${MODELOS_EMB[@]}"),
   $(lista "arn:aws:bedrock:$REGION:$CUENTA_AWS:inference-profile/" "${PERFILES_CLAUDE[@]}"),
   $(lista "arn:aws:bedrock:us-*::foundation-model/" "${MODELOS_CLAUDE[@]}")]},
 {"Sid":"Buckets","Effect":"Allow","Action":["s3:CreateBucket","s3:DeleteBucket","s3:ListBucket","s3:GetObject","s3:PutObject","s3:DeleteObject",
   "s3:PutBucketTagging","s3:GetBucketTagging","s3:PutBucketPublicAccessBlock","s3:PutEncryptionConfiguration"],
  "Resource":["arn:aws:s3:::$S3_DOCS","arn:aws:s3:::$S3_DOCS/*"]},
 {"Sid":"VectorBucket","Effect":"Allow","Action":"s3vectors:*",
  "Resource":["arn:aws:s3vectors:$REGION:$CUENTA_AWS:bucket/$S3_VECTORES","arn:aws:s3vectors:$REGION:$CUENTA_AWS:bucket/$S3_VECTORES/index/*"]},
 {"Sid":"PasarRolKB","Effect":"Allow","Action":"iam:PassRole","Resource":"arn:aws:iam::$CUENTA_AWS:role/$ROL_KB",
  "Condition":{"StringEquals":{"iam:PassedToService":"bedrock.amazonaws.com"}}}]}
J
crear_rol "$ROL_OPERADOR" $TMP/confianza_op.json
aws iam put-role-policy --role-name "$ROL_OPERADOR" --policy-name "${PREFIJO}-operador" --policy-document file://$TMP/permisos_op.json

# 4. Perfil local `semana12` (en ~/.aws/config, fuera del repo) que asume el rol operador con la sesión actual.
aws configure set profile.$PERFIL_AWS.role_arn "arn:aws:iam::$CUENTA_AWS:role/$ROL_OPERADOR"
aws configure set profile.$PERFIL_AWS.source_profile "${AWS_PROFILE:-default}"
aws configure set profile.$PERFIL_AWS.region "$REGION"
sleep 10  # propagación de IAM
aws sts get-caller-identity --profile $PERFIL_AWS --query Arn --output text | sed 's/^/perfil semana12 asume: /'
rm -rf $TMP
echo "AWS listo. Usa --profile $PERFIL_AWS (o AWS_PROFILE=$PERFIL_AWS) en los scripts de la semana."
