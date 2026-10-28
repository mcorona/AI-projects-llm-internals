#!/usr/bin/env bash
# Semana 12, actividad 4: crea y llena las Knowledge Bases de Bedrock (con el rol operador, perfil semana12).
#   1. bucket de documentos semana12-docs-<cuenta> (privado) y subida del paquete de ingesta (actividad 2);
#   2. vector bucket semana12-vectores-<cuenta> con un índice por configuración (1024 dimensiones, coseno, float32;
#      texto y metadatos internos de Bedrock como no filtrables, para que tenant_id y roles sí lo sean);
#   3. una Knowledge Base por configuración (embeddings Cohere Embed Multilingual v3) con su data source e ingesta.
# Configuraciones (CONFIGS="..." para elegir; por defecto todas):
#   adm-pred      originales (administrado/), chunking predeterminado de Bedrock, parser predeterminado
#   adm-fijo      originales, tamaño fijo 100 tokens con 20 % de solape (lo más cercano a 400/80 caracteres)
#   adm-fijo-bda  como adm-fijo, con el parser Bedrock Data Automation (PDF e imágenes)
#   ctl-chunks    chunks del pipeline propio (controlado/chunks/), sin re-trocear (chunking NONE)
# Idempotente: reutiliza lo que ya existe por nombre. Escribe los ids en estado_aws.json (fuera de Git).
set -euo pipefail
cd "$(dirname "$0")"; source config.sh
export AWS_PROFILE=$PERFIL_AWS AWS_PAGER=""
R="--region $REGION"
PAQUETE=../ingesta/paquete
EMB="arn:aws:bedrock:$REGION::foundation-model/cohere.embed-multilingual-v3"
ROL_KB_ARN="arn:aws:iam::$CUENTA_AWS:role/$ROL_KB"
CONFIGS=${CONFIGS:-"adm-pred adm-fijo adm-fijo-bda ctl-chunks"}
ESTADO=estado_aws.json; [ -f $ESTADO ] || echo '{}' > $ESTADO
echo "como $(aws sts get-caller-identity --query Arn --output text)"

# 1. Bucket de documentos y subida del paquete
if ! aws s3api head-bucket --bucket $S3_DOCS 2>/dev/null; then
  aws s3api create-bucket --bucket $S3_DOCS $R >/dev/null
  aws s3api put-public-access-block --bucket $S3_DOCS --public-access-block-configuration \
    BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true
  aws s3api put-bucket-tagging --bucket $S3_DOCS --tagging "TagSet=[{Key=$ETIQUETA_CLAVE,Value=$ETIQUETA_VALOR}]"
  echo "bucket $S3_DOCS: creado (privado)"
fi
aws s3 sync $PAQUETE s3://$S3_DOCS/ --exclude "vertex_*" --exclude "manifiesto.json" --delete --only-show-errors
echo "paquete subido: $(aws s3 ls s3://$S3_DOCS/ --recursive | wc -l | tr -d ' ') objetos"

# 2. Vector bucket
aws s3vectors get-vector-bucket --vector-bucket-name $S3_VECTORES $R >/dev/null 2>&1 || \
  { aws s3vectors create-vector-bucket --vector-bucket-name $S3_VECTORES $R >/dev/null; echo "vector bucket $S3_VECTORES: creado"; }

ingesta() {  # config, prefijo, configuración de ingesta (JSON o vacío)
  local cfg=$1 pref=$2 vic=$3 nombre="$PREFIJO-$1" idx="$1"
  aws s3vectors get-index --vector-bucket-name $S3_VECTORES --index-name $idx $R >/dev/null 2>&1 || \
    aws s3vectors create-index --vector-bucket-name $S3_VECTORES --index-name $idx --data-type float32 --dimension 1024 \
      --distance-metric cosine --metadata-configuration '{"nonFilterableMetadataKeys":["AMAZON_BEDROCK_TEXT","AMAZON_BEDROCK_METADATA"]}' $R
  local idx_arn; idx_arn=$(aws s3vectors get-index --vector-bucket-name $S3_VECTORES --index-name $idx $R --query index.indexArn --output text)
  local kb; kb=$(aws bedrock-agent list-knowledge-bases $R --query "knowledgeBaseSummaries[?name=='$nombre'].knowledgeBaseId" --output text)
  if [ -z "$kb" ]; then
    kb=$(aws bedrock-agent create-knowledge-base $R --name $nombre --role-arn $ROL_KB_ARN \
      --knowledge-base-configuration "{\"type\":\"VECTOR\",\"vectorKnowledgeBaseConfiguration\":{\"embeddingModelArn\":\"$EMB\"}}" \
      --storage-configuration "{\"type\":\"S3_VECTORS\",\"s3VectorsConfiguration\":{\"indexArn\":\"$idx_arn\"}}" \
      --tags $ETIQUETA_CLAVE=$ETIQUETA_VALOR --query knowledgeBase.knowledgeBaseId --output text)
    echo "KB $nombre: creada ($kb)"
  fi
  until [ "$(aws bedrock-agent get-knowledge-base $R --knowledge-base-id $kb --query knowledgeBase.status --output text)" = ACTIVE ]; do sleep 5; done
  local ds; ds=$(aws bedrock-agent list-data-sources $R --knowledge-base-id $kb --query 'dataSourceSummaries[0].dataSourceId' --output text)
  if [ "$ds" = "None" ] || [ -z "$ds" ]; then
    local args=(--knowledge-base-id $kb --name "$nombre-ds" --data-deletion-policy DELETE
      --data-source-configuration "{\"type\":\"S3\",\"s3Configuration\":{\"bucketArn\":\"arn:aws:s3:::$S3_DOCS\",\"inclusionPrefixes\":[\"$pref\"]}}")
    [ -n "$vic" ] && args+=(--vector-ingestion-configuration "$vic")
    ds=$(aws bedrock-agent create-data-source $R "${args[@]}" --query dataSource.dataSourceId --output text)
    echo "data source $nombre-ds: creado ($ds)"
  fi
  local job; job=$(aws bedrock-agent start-ingestion-job $R --knowledge-base-id $kb --data-source-id $ds --query ingestionJob.ingestionJobId --output text)
  local t0=$SECONDS st
  while :; do
    st=$(aws bedrock-agent get-ingestion-job $R --knowledge-base-id $kb --data-source-id $ds --ingestion-job-id $job --query ingestionJob.status --output text)
    case $st in COMPLETE|FAILED|STOPPED) break;; esac; sleep 10
  done
  echo "ingesta $nombre: $st en $((SECONDS - t0)) s"
  aws bedrock-agent get-ingestion-job $R --knowledge-base-id $kb --data-source-id $ds --ingestion-job-id $job \
    --query 'ingestionJob.[statistics, failureReasons]' --output json | python3 -c "
import json,sys
s,f=json.load(sys.stdin); print('  ', {k:v for k,v in s.items() if v})
for x in (f or []):
    try: partes=json.loads(x)
    except Exception: partes=[x]
    for y in (partes if isinstance(partes,list) else [partes]): print('   fallo:', str(y)[:400])"
  python3 - "$ESTADO" "$cfg" "$kb" "$ds" "$idx_arn" "$st" "$((SECONDS - t0))" <<'P'
import json, sys
ruta, cfg, kb, ds, idx, st, seg = sys.argv[1:]
e = json.load(open(ruta)); e[cfg] = {"kb_id": kb, "ds_id": ds, "index_arn": idx, "ingesta": st, "ingesta_s": int(seg)}
json.dump(e, open(ruta, "w"), indent=1)
P
}

FIJO='"chunkingConfiguration":{"chunkingStrategy":"FIXED_SIZE","fixedSizeChunkingConfiguration":{"maxTokens":100,"overlapPercentage":20}}'
for cfg in $CONFIGS; do
  case $cfg in
    adm-pred)     ingesta $cfg administrado/ "" ;;
    adm-fijo)     ingesta $cfg administrado/ "{$FIJO}" ;;
    adm-fijo-bda) ingesta $cfg administrado/ "{$FIJO,\"parsingConfiguration\":{\"parsingStrategy\":\"BEDROCK_DATA_AUTOMATION\",\"bedrockDataAutomationConfiguration\":{\"parsingModality\":\"MULTIMODAL\"}}}" ;;
    ctl-chunks)   ingesta $cfg controlado/chunks/ '{"chunkingConfiguration":{"chunkingStrategy":"NONE"}}' ;;
    *) echo "configuración desconocida: $cfg"; exit 1 ;;
  esac
done
echo; cat $ESTADO
