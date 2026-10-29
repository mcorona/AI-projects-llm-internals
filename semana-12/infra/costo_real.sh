#!/usr/bin/env bash
# Semana 12, actividad 10: costo real de la semana en AWS, por servicio y por día, desde Cost Explorer. Solo lectura.
#   ./costo_real.sh [inicio] [fin]      fechas AAAA-MM-DD; fin exclusivo. Por defecto 2026-10-26 a mañana.
# Cada consulta a la API de Cost Explorer cuesta $0.01; este script hace UNA. Los datos tardan de 24 a 48 h en
# consolidarse, así que se corre de nuevo el día 2 después del borrado. El costo es de toda la cuenta (el presupuesto
# también lo es): se separan los servicios que usó la semana 12 de los demás.
set -euo pipefail
cd "$(dirname "$0")"; source config.sh
export AWS_PAGER=""
INI=${1:-2026-10-26}; FIN=${2:-$(python3 -c 'import datetime;print(datetime.date.today()+datetime.timedelta(days=1))')}
aws ce get-cost-and-usage --region us-east-1 --time-period Start=$INI,End=$FIN --granularity DAILY \
  --metrics UnblendedCost --group-by Type=DIMENSION,Key=SERVICE --output json | python3 costo_real.py
echo
echo "Google Cloud (sin API de costos sin exportación a BigQuery): consola > Facturación > Informes, proyecto $GCP_PROYECTO,"
echo "  agrupar por SKU, del $INI a hoy: https://console.cloud.google.com/billing/reports?project=$GCP_PROYECTO"
echo "Anthropic API (generador y juez Haiku 5.5): https://console.anthropic.com/usage   ·   OpenAI (embeddings de answer relevancy en CI): https://platform.openai.com/usage"
