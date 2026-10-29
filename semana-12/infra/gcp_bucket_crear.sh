#!/usr/bin/env bash
# Semana 12, actividad 5 (lo corre el dueño del proyecto): bucket de documentos en GCS y permisos solo sobre ese bucket.
# - la cuenta de servicio semana12-operador puede leer y escribir objetos del bucket (roles/storage.objectAdmin en el bucket);
# - el agente de servicio de Discovery Engine puede leerlos para importarlos (roles/storage.objectViewer en el bucket).
set -euo pipefail
cd "$(dirname "$0")"; source config.sh
P=$GCP_PROYECTO
NUM=$(gcloud projects describe $P --format='value(projectNumber)')
if ! gcloud storage buckets describe gs://$GCS_DOCS --project=$P >/dev/null 2>&1; then
  gcloud storage buckets create gs://$GCS_DOCS --project=$P --location=US --uniform-bucket-level-access \
    --public-access-prevention --default-storage-class=STANDARD
  gcloud storage buckets update gs://$GCS_DOCS --update-labels=$ETIQUETA_CLAVE=$ETIQUETA_VALOR
  echo "bucket gs://$GCS_DOCS: creado (privado, US)"
fi
# El agente de servicio de Discovery Engine existe tras activar la API; se fuerza su creación por si aún no existe.
gcloud beta services identity create --service=discoveryengine.googleapis.com --project=$P >/dev/null 2>&1 || true
gcloud storage buckets add-iam-policy-binding gs://$GCS_DOCS --member=serviceAccount:$GCP_SA_EMAIL --role=roles/storage.objectAdmin >/dev/null
gcloud storage buckets add-iam-policy-binding gs://$GCS_DOCS \
  --member=serviceAccount:service-$NUM@gcp-sa-discoveryengine.iam.gserviceaccount.com --role=roles/storage.objectViewer >/dev/null
echo "permisos en gs://$GCS_DOCS: $GCP_SA (objectAdmin), agente de Discovery Engine (objectViewer)"
