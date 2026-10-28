#!/usr/bin/env bash
# Semana 12 (Google Cloud): borra apps (engines), data stores, bucket de documentos y la cuenta de servicio de la semana.
#   ./gcp_borrar.sh                          simulación (por defecto)
#   ./gcp_borrar.sh --confirmar              borra
#   ./gcp_borrar.sh --confirmar --presupuesto   además borra el presupuesto (después de revisar la factura)
# Solo toca recursos con el prefijo semana12 en el proyecto de config.sh. Requiere sesión del dueño (gcloud auth login).
set -uo pipefail
cd "$(dirname "$0")"; source config.sh
HAZ=0; PRES=0; for a in "$@"; do [ "$a" = "--confirmar" ] && HAZ=1; [ "$a" = "--presupuesto" ] && PRES=1; done
P=$GCP_PROYECTO
TOKEN=$(gcloud auth print-access-token)
API="https://discoveryengine.googleapis.com/v1/projects/$P/locations/$GCP_UBICACION/collections/default_collection"
api() { curl -s -X "$1" -H "Authorization: Bearer $TOKEN" -H "x-goog-user-project: $P" "$2"; }
nombres() { python3 -c "import json,sys; d=json.load(sys.stdin); [print(x['name']) for x in d.get('$1',[]) if x['name'].split('/')[-1].startswith('$PREFIJO')]"; }
run_del() { if [ $HAZ -eq 1 ]; then echo "+ DELETE $1"; api DELETE "https://discoveryengine.googleapis.com/v1/$1" | grep -o '"name": "[^"]*' | head -1; else echo "[simulación] DELETE $1"; fi; }
run() { if [ $HAZ -eq 1 ]; then echo "+ $*"; "$@" >/dev/null 2>&1 || echo "  (falló: $*)"; else echo "[simulación] $*"; fi; }

for e in $(api GET "$API/engines" | nombres engines); do run_del "$e"; done      # apps antes que data stores
[ $HAZ -eq 1 ] && sleep 10
for d in $(api GET "$API/dataStores" | nombres dataStores); do run_del "$d"; done
for b in $(gcloud storage buckets list --project=$P --format='value(name)' | grep "^$PREFIJO"); do
  run gcloud storage rm --recursive gs://$b
done
gcloud iam service-accounts describe $GCP_SA_EMAIL --project=$P >/dev/null 2>&1 && \
  { run gcloud projects remove-iam-policy-binding $P --member=serviceAccount:$GCP_SA_EMAIL --role=roles/discoveryengine.editor --condition=None
    run gcloud iam service-accounts delete $GCP_SA_EMAIL --project=$P --quiet; }
if [ $PRES -eq 1 ]; then
  CTA=$(gcloud billing projects describe $P --format='value(billingAccountName.basename())')
  for b in $(gcloud billing budgets list --billing-account=$CTA --filter="displayName=$PREFIJO" --format='value(name)'); do
    run gcloud billing budgets delete $b --quiet
  done
fi
echo; ./inventario.sh gcp
