#!/usr/bin/env bash
# Semana 12 (AWS): borra todo lo que crea la semana, en orden de dependencias. Lo corre un administrador.
#   ./aws_borrar.sh                         muestra lo que borraría (simulación, por defecto)
#   ./aws_borrar.sh --confirmar             borra KB, data sources, vector bucket, bucket de documentos y roles
#   ./aws_borrar.sh --confirmar --presupuesto   además borra el presupuesto (solo después de revisar la factura)
# Solo toca recursos con el prefijo semana12; no toca otros buckets ni presupuestos de la cuenta.
set -uo pipefail
cd "$(dirname "$0")"; source config.sh
export AWS_PAGER=""
HAZ=0; PRES=0; for a in "$@"; do [ "$a" = "--confirmar" ] && HAZ=1; [ "$a" = "--presupuesto" ] && PRES=1; done
run() { if [ $HAZ -eq 1 ]; then echo "+ $*"; "$@" >/dev/null || echo "  (falló: $*)"; else echo "[simulación] $*"; fi; }
R="--region $REGION"

# 1. Knowledge Bases con prefijo y sus data sources. Cada data source pasa primero a dataDeletionPolicy RETAIN: así la KB
#    no intenta borrar sus vectores (se van con el vector bucket en el paso 2). Sin esto, la KB queda en DELETE_UNSUCCESSFUL
#    si el índice o el rol desaparecen antes de que termine. Los índices y roles solo se borran cuando ya no queda ninguna KB.
retener() {
  local f; f=$(mktemp)
  aws bedrock-agent get-data-source $R --knowledge-base-id $1 --data-source-id $2 --output json | python3 -c '
import json, sys
d = json.load(sys.stdin)["dataSource"]
campos = ("knowledgeBaseId", "dataSourceId", "name", "description", "dataSourceConfiguration",
          "vectorIngestionConfiguration", "serverSideEncryptionConfiguration")
o = {k: d[k] for k in campos if k in d}
o["dataDeletionPolicy"] = "RETAIN"
print(json.dumps(o))' > $f
  run aws bedrock-agent update-data-source $R --cli-input-json file://$f
  rm -f $f
}
kbs() { aws bedrock-agent list-knowledge-bases $R --query "knowledgeBaseSummaries[?starts_with(name,'$PREFIJO')].$1" --output text; }
for kb in $(kbs knowledgeBaseId); do
  for ds in $(aws bedrock-agent list-data-sources $R --knowledge-base-id $kb --query 'dataSourceSummaries[].dataSourceId' --output text); do
    retener $kb $ds
    run aws bedrock-agent delete-data-source $R --knowledge-base-id $kb --data-source-id $ds
  done
  run aws bedrock-agent delete-knowledge-base $R --knowledge-base-id $kb
done
if [ $HAZ -eq 1 ]; then
  for i in $(seq 1 30); do
    sleep 10; EST=$(kbs status)
    [ -z "$EST" ] && { echo "Knowledge Bases: borradas"; break; }
    if echo "$EST" | grep -q DELETE_UNSUCCESSFUL; then
      echo "Knowledge Bases con DELETE_UNSUCCESSFUL; no se borran índices ni roles todavía:"
      for kb in $(kbs knowledgeBaseId); do
        echo "  $kb: $(aws bedrock-agent get-knowledge-base $R --knowledge-base-id $kb --query 'knowledgeBase.[status,failureReasons]' --output text)"
      done
      exit 1
    fi
    echo "  esperando el borrado de las Knowledge Bases ($EST)"
  done
  [ -n "$(kbs status)" ] && { echo "Las Knowledge Bases no terminaron de borrarse en 5 min; vuelve a correr el script."; exit 1; }
fi

# 2. Vector buckets con prefijo: índices y bucket.
for vb in $(aws s3vectors list-vector-buckets $R --query "vectorBuckets[?starts_with(vectorBucketName,'$PREFIJO')].vectorBucketName" --output text); do
  for ix in $(aws s3vectors list-indexes $R --vector-bucket-name $vb --query 'indexes[].indexName' --output text); do
    run aws s3vectors delete-index $R --vector-bucket-name $vb --index-name $ix
  done
  run aws s3vectors delete-vector-bucket $R --vector-bucket-name $vb
done

# 3. Buckets de S3 con prefijo: vaciar y borrar.
for b in $(aws s3api list-buckets --query "Buckets[?starts_with(Name,'$PREFIJO')].Name" --output text); do
  run aws s3 rm s3://$b --recursive
  run aws s3api delete-bucket --bucket $b $R
done

# 4. Roles con prefijo (políticas en línea primero).
for rol in $(aws iam list-roles --query "Roles[?starts_with(RoleName,'$PREFIJO')].RoleName" --output text); do
  for pol in $(aws iam list-role-policies --role-name $rol --query 'PolicyNames' --output text); do
    run aws iam delete-role-policy --role-name $rol --policy-name $pol
  done
  run aws iam delete-role --role-name $rol
done
[ $HAZ -eq 1 ] && { aws configure set profile.$PERFIL_AWS.role_arn ""; echo "perfil $PERFIL_AWS: role_arn vaciado"; }

# 5. Proveedor OIDC de GitHub (actividad 9), solo si lo creó la semana 12 (etiqueta proyecto=semana12).
for prov in $(aws iam list-open-id-connect-providers --query "OpenIDConnectProviderList[?contains(Arn,'token.actions.githubusercontent.com')].Arn" --output text); do
  if aws iam list-open-id-connect-provider-tags --open-id-connect-provider-arn $prov --query "Tags[?Key=='$ETIQUETA_CLAVE' && Value=='$ETIQUETA_VALOR']" --output text | grep -q .; then
    run aws iam delete-open-id-connect-provider --open-id-connect-provider-arn $prov
  fi
done

# 6. Presupuesto, solo si se pide.
if [ $PRES -eq 1 ]; then run aws budgets delete-budget --account-id "$CUENTA_AWS" --budget-name "$PREFIJO"; fi
echo; ./inventario.sh aws
