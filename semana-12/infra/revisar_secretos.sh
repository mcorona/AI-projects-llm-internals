#!/usr/bin/env bash
# Revisa que no haya credenciales en los archivos versionados (o por versionar) del repo. Sale con 1 si encuentra algo.
# Patrones: llaves de acceso de AWS, llaves privadas (cuentas de servicio de Google), API keys de Google, Anthropic y OpenAI.
set -uo pipefail
cd "$(git rev-parse --show-toplevel)"
PATRON='(AKIA|ASIA)[0-9A-Z]{16}|aws_secret_access_key *= *[A-Za-z0-9/+]{30,}|-----BEGIN [A-Z ]*PRIVATE KEY-----|"private_key_id": *"[0-9a-f]{20,}|AIza[0-9A-Za-z_-]{35}|sk-ant-[A-Za-z0-9_-]{20,}|sk-proj-[A-Za-z0-9_-]{20,}'
HALLAZGOS=$( { git ls-files; git ls-files --others --exclude-standard; } | grep -v -E '\.(png|jpg|jpeg|pdf|gif)$' | \
  xargs -I{} grep -I -n -E "$PATRON" {} /dev/null 2>/dev/null | grep -v "revisar_secretos.sh" )
if [ -n "$HALLAZGOS" ]; then echo "Posibles credenciales:"; echo "$HALLAZGOS" | cut -c1-160; exit 1; fi
echo "Sin credenciales en los archivos del repo."
