#!/usr/bin/env bash
# Semana 12, actividad 1 (Google Cloud): presupuesto con alertas y cuenta de servicio con permisos mínimos que se usa por
# impersonación (sin archivos de llave). Idempotente. Lo corre el dueño del proyecto. No crea recursos facturables.
set -euo pipefail
cd "$(dirname "$0")"; source config.sh
P=$GCP_PROYECTO
YO=$(gcloud config get-value account 2>/dev/null)
echo "proyecto $P, como $YO"
gcloud services enable billingbudgets.googleapis.com iamcredentials.googleapis.com iam.googleapis.com --project=$P

# 1. Presupuesto limitado al proyecto, con alertas al 50, 90 y 100 % (correo a los administradores de facturación).
CTA=$(gcloud billing projects describe $P --format='value(billingAccountName.basename())')
if gcloud billing budgets list --billing-account=$CTA --format='value(displayName)' | grep -qx "$PREFIJO"; then
  echo "presupuesto $PREFIJO: ya existe"
else
  # El monto va en la moneda de la cuenta de facturación (una cuenta de México factura en MXN).
  MONEDA=$(gcloud billing accounts describe $CTA --format='value(currencyCode)')
  if [ "$MONEDA" = "USD" ]; then MONTO=$PRESUPUESTO_USD; else MONTO=${PRESUPUESTO_GCP_LOCAL:?Define PRESUPUESTO_GCP_LOCAL con el equivalente a $PRESUPUESTO_USD USD en $MONEDA}; fi
  echo "moneda de la cuenta de facturación: $MONEDA; presupuesto: $MONTO $MONEDA"
  gcloud billing budgets create --billing-account=$CTA --display-name="$PREFIJO" --budget-amount=${MONTO}${MONEDA} \
    --filter-projects=projects/$P --threshold-rule=percent=0.5 --threshold-rule=percent=0.9 --threshold-rule=percent=1.0 \
    --threshold-rule=percent=1.0,basis=forecasted-spend >/dev/null
  echo "presupuesto $PREFIJO: creado ($MONTO $MONEDA, solo el proyecto $P)"
fi

# 2. Cuenta de servicio operadora: Discovery Engine (crear y consultar data stores y apps) y nada más a nivel proyecto.
#    El acceso al bucket de documentos se da en el propio bucket cuando se crea (actividad 2), no a nivel proyecto.
if ! gcloud iam service-accounts describe $GCP_SA_EMAIL --project=$P >/dev/null 2>&1; then
  gcloud iam service-accounts create $GCP_SA --project=$P --display-name="Semana 12: operador de Vertex AI Search"
fi
gcloud projects add-iam-policy-binding $P --member=serviceAccount:$GCP_SA_EMAIL --role=roles/discoveryengine.editor --condition=None >/dev/null
# Usar el proyecto como proyecto de cuota (x-goog-user-project) requiere serviceusage.services.use.
gcloud projects add-iam-policy-binding $P --member=serviceAccount:$GCP_SA_EMAIL --role=roles/serviceusage.serviceUsageConsumer --condition=None >/dev/null
# 3. Solo tu usuario puede generar tokens de la cuenta de servicio (impersonación); no se crean llaves.
gcloud iam service-accounts add-iam-policy-binding $GCP_SA_EMAIL --project=$P \
  --member=user:$YO --role=roles/iam.serviceAccountTokenCreator >/dev/null
N=$(gcloud iam service-accounts keys list --iam-account=$GCP_SA_EMAIL --managed-by=user --format='value(name)' | wc -l | tr -d ' ')
echo "cuenta de servicio $GCP_SA_EMAIL: roles/discoveryengine.editor y serviceusage.serviceUsageConsumer; llaves de usuario: $N (deben ser 0)"
sleep 20  # propagación de IAM
gcloud auth print-access-token --impersonate-service-account=$GCP_SA_EMAIL >/dev/null 2>&1 \
  && echo "impersonación: OK" || echo "impersonación: aún no propaga; repite en 1 minuto"
echo "Google Cloud listo. Para la semana: gcloud auth application-default login --impersonate-service-account=$GCP_SA_EMAIL"
