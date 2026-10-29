#!/usr/bin/env bash
# Semana 12, actividad 9 (AWS, lo corre el administrador): rol semana12-ci que solo puede asumir, por OIDC de GitHub
# Actions, un job del entorno nube-semana12 de este repo. Sin llaves de acceso. Permisos de solo consulta: Retrieve,
# RetrieveAndGenerate e invocar los modelos que usan (Haiku y embeddings). No puede crear ni borrar nada.
set -euo pipefail
cd "$(dirname "$0")"; source config.sh
export AWS_PAGER=""
SUJETO=$(gh_sujeto)
TMP=$(mktemp -d)
PROV=$(aws iam list-open-id-connect-providers --query "OpenIDConnectProviderList[?contains(Arn,'token.actions.githubusercontent.com')].Arn" --output text)
if [ -z "$PROV" ]; then
  PROV=$(aws iam create-open-id-connect-provider --url https://token.actions.githubusercontent.com --client-id-list sts.amazonaws.com \
    --tags Key=$ETIQUETA_CLAVE,Value=$ETIQUETA_VALOR --query OpenIDConnectProviderArn --output text)
  echo "proveedor OIDC de GitHub: creado ($PROV)"
else
  echo "proveedor OIDC de GitHub: ya existía ($PROV); no se borra en la actividad 10 si no lo creó la semana 12"
fi
cat > $TMP/confianza.json <<J
{"Version":"2012-10-17","Statement":[{"Effect":"Allow","Principal":{"Federated":"$PROV"},"Action":"sts:AssumeRoleWithWebIdentity",
 "Condition":{"StringEquals":{"token.actions.githubusercontent.com:aud":"sts.amazonaws.com",
   "token.actions.githubusercontent.com:sub":"$SUJETO"}}}]}
J
lista() { local p=$1; shift; local out=""; for x in "$@"; do out+="\"${p}${x}\","; done; echo "${out%,}"; }
cat > $TMP/permisos.json <<J
{"Version":"2012-10-17","Statement":[
 {"Sid":"Lectura","Effect":"Allow","Action":["bedrock:ListKnowledgeBases","bedrock:GetInferenceProfile"],"Resource":"*"},
 {"Sid":"Consultar","Effect":"Allow","Action":["bedrock:Retrieve","bedrock:GetKnowledgeBase"],"Resource":"arn:aws:bedrock:$REGION:$CUENTA_AWS:knowledge-base/*"},
 {"Sid":"RetrieveAndGenerate","Effect":"Allow","Action":["bedrock:RetrieveAndGenerate"],"Resource":"*"},
 {"Sid":"Modelos","Effect":"Allow","Action":["bedrock:InvokeModel"],"Resource":[
   $(lista "arn:aws:bedrock:$REGION::foundation-model/" "${MODELOS_EMB[@]}"),
   $(lista "arn:aws:bedrock:$REGION:$CUENTA_AWS:inference-profile/" "${PERFILES_CLAUDE[@]}"),
   $(lista "arn:aws:bedrock:us-*::foundation-model/" "${MODELOS_CLAUDE[@]}")]}]}
J
if aws iam get-role --role-name $ROL_CI >/dev/null 2>&1; then
  aws iam update-assume-role-policy --role-name $ROL_CI --policy-document file://$TMP/confianza.json
else
  aws iam create-role --role-name $ROL_CI --assume-role-policy-document file://$TMP/confianza.json \
    --tags Key=$ETIQUETA_CLAVE,Value=$ETIQUETA_VALOR --max-session-duration 3600 >/dev/null
fi
aws iam put-role-policy --role-name $ROL_CI --policy-name ${PREFIJO}-ci --policy-document file://$TMP/permisos.json
rm -rf $TMP
echo "rol $ROL_CI: arn:aws:iam::$CUENTA_AWS:role/$ROL_CI (solo $SUJETO)"
