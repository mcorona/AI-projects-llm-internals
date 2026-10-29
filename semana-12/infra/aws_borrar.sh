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

# 1. Knowledge Bases con prefijo y sus data sources.
for kb in $(aws bedrock-agent list-knowledge-bases $R --query "knowledgeBaseSummaries[?starts_with(name,'$PREFIJO')].knowledgeBaseId" --output text); do
  for ds in $(aws bedrock-agent list-data-sources $R --knowledge-base-id $kb --query 'dataSourceSummaries[].dataSourceId' --output text); do
    run aws bedrock-agent delete-data-source $R --knowledge-base-id $kb --data-source-id $ds
  done
  run aws bedrock-agent delete-knowledge-base $R --knowledge-base-id $kb
done
[ $HAZ -eq 1 ] && sleep 15

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
