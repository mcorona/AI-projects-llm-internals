#!/usr/bin/env bash
# Semana 14, actividad 4: arranca Keycloak con el realm legacybridge y fija las contraseñas de los usuarios de prueba.
# Idempotente: correrlo de nuevo no duplica nada (el realm solo se importa si no existe; las contraseñas se vuelven a
# fijar con los mismos valores). Los secretos se generan una vez en .secretos.env (chmod 600, ignorado por Git).
#
#   ./arrancar.sh             arranca (o confirma que ya corre) y configura
#   ./arrancar.sh --detener   detiene el contenedor (conserva datos)
#   ./arrancar.sh --borrar    detiene y borra el volumen (el siguiente arranque reimporta el realm)
#
# KC_MODO=externo usa un Keycloak que ya corre en $KC_URL y $KCADM (ruta a kcadm.sh) en lugar de Docker.
set -euo pipefail
DIR="$(cd "$(dirname "$0")" && pwd)"
SECRETOS="$DIR/.secretos.env"
COMPOSE=(docker compose -f "$DIR/docker-compose.yml" --env-file "$SECRETOS")
KC_URL="${KC_URL:-http://127.0.0.1:8080}"
REALM=legacybridge
MODO="${KC_MODO:-docker}"
USUARIOS=(analista almacenista vendedor)

aleatorio() { LC_ALL=C tr -dc 'A-Za-z0-9' </dev/urandom | head -c 24; }

if [[ ! -f "$SECRETOS" ]]; then
  umask 077
  {
    echo "# Generado por arrancar.sh el $(date -u +%FT%TZ). No versionar."
    echo "KC_BOOTSTRAP_ADMIN_USERNAME=admin"
    echo "KC_BOOTSTRAP_ADMIN_PASSWORD=$(aleatorio)"
    for u in "${USUARIOS[@]}"; do echo "KC_PWD_$(echo "$u" | tr '[:lower:]' '[:upper:]')=$(aleatorio)"; done
  } >"$SECRETOS"
  echo "[auth] secretos nuevos en $SECRETOS"
fi
chmod 600 "$SECRETOS"
set -a; source "$SECRETOS"; set +a

case "${1:-}" in
  --detener) "${COMPOSE[@]}" stop; exit 0 ;;
  --borrar) "${COMPOSE[@]}" down -v; exit 0 ;;
  "") ;;
  *) echo "uso: $0 [--detener|--borrar]" >&2; exit 2 ;;
esac

if [[ "$MODO" == docker ]]; then
  "${COMPOSE[@]}" up -d --quiet-pull
  KCADM=("${COMPOSE[@]}" exec -T keycloak /opt/keycloak/bin/kcadm.sh)
  KCADM_SERVER=http://localhost:8080
  KCADM_CONFIG=/tmp/kcadm.config            # dentro del contenedor
else
  : "${KCADM:?con KC_MODO=externo define KCADM=/ruta/a/kcadm.sh}"
  KCADM=("$KCADM")
  KCADM_SERVER="$KC_URL"
  KCADM_CONFIG="$(mktemp)"; trap 'rm -f "$KCADM_CONFIG"' EXIT
fi

echo -n "[auth] esperando a Keycloak en $KC_URL "
for _ in $(seq 1 90); do
  if curl -fsS "$KC_URL/realms/$REALM/.well-known/openid-configuration" >/dev/null 2>&1; then echo " listo"; break; fi
  echo -n "."; sleep 2
done
curl -fsS "$KC_URL/realms/$REALM/.well-known/openid-configuration" >/dev/null || { echo " no respondió" >&2; exit 1; }

kc() { "${KCADM[@]}" "$@" --config "$KCADM_CONFIG"; }
kc config credentials --server "$KCADM_SERVER" --realm master \
   --user "$KC_BOOTSTRAP_ADMIN_USERNAME" --password "$KC_BOOTSTRAP_ADMIN_PASSWORD" >/dev/null 2>&1
for u in "${USUARIOS[@]}"; do
  var="KC_PWD_$(echo "$u" | tr '[:lower:]' '[:upper:]')"
  kc set-password -r "$REALM" --username "$u" --new-password "${!var}"
done
recurso=$(kc get clients -r "$REALM" -q clientId=legado-mcp --fields 'attributes(resource_url)' | grep -o '"resource_url" *: *"[^"]*"' || true)
echo "[auth] realm $REALM listo: ${#USUARIOS[@]} usuarios con contraseña; $recurso"
echo "[auth] emisor: $KC_URL/realms/$REALM  (contraseñas en $SECRETOS)"
