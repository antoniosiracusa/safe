#!/bin/bash
# Rilascio o aggiornamento: rigenera i file da .env, scarica le immagini, applica le migrazioni,
# riavvia i servizi. Idempotente.
#
#   ./deploy.sh              # usa le immagini indicate in .env (API_IMAGE / WEB_IMAGE)
#   ./deploy.sh v1.2.0       # fissa un tag di rilascio per api e web e lo scrive in .env
set -euo pipefail
cd "$(dirname "$0")"
COMPOSE="docker compose --env-file .env -f docker-compose.prod.yml"

if [ "${1:-}" != "" ]; then
  sed -i "s#^API_IMAGE=.*#API_IMAGE=ghcr.io/antoniosiracusa/safe-api:$1#; s#^WEB_IMAGE=.*#WEB_IMAGE=ghcr.io/antoniosiracusa/safe-web:$1#" .env
  echo "immagini fissate al tag $1"
fi

./render.sh
# solo le immagini applicative: quelle di terze parti (db, redis, keycloak, minio) restano quelle
# installate e si aggiornano di proposito (Docker Hub può negare pull anonimi, es. minio/minio)
$COMPOSE pull --quiet api web $( [ "${COMPOSE_PROFILES:-}" = "beta" ] && echo web-beta )
$COMPOSE up -d --wait db redis   # attende gli healthcheck (al primo avvio initdb richiede qualche secondo)
$COMPOSE run --rm --no-deps api python manage.py migrate --noinput   # include seed di vocabolari e ruoli
$COMPOSE up -d --remove-orphans
$COMPOSE ps
DOMAIN="${DOMAIN:-$(grep ^DOMAIN= .env | cut -d= -f2)}"
# la SPA risponde 200 su qualsiasi percorso: verifichiamo che /api risponda davvero con il JSON dell'API
for i in $(seq 1 30); do
  body=$(curl -fsS "https://${DOMAIN}/api/v1/health" 2>/dev/null || true)
  case "$body" in *'"status":"ok"'*) echo "ok: https://${DOMAIN}/ (api: $body)"; exit 0;; esac
  sleep 5
done
echo "ERRORE: l'API non risponde su https://${DOMAIN}/api/v1/health (vedi: docker compose ps, logs api)" >&2
exit 1
