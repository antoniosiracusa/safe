#!/bin/bash
# Genera i file dipendenti da .env: configurazione runtime della SPA e realm Keycloak di produzione.
# Va rieseguito dopo ogni modifica di .env (deploy.sh lo fa automaticamente).
set -euo pipefail
cd "$(dirname "$0")"
set -a; source ./.env; set +a
mkdir -p generated

cat > generated/app-config.json <<JSON
{
  "version": "$(cat VERSION 2>/dev/null || echo 1.0.0)",
  "oidc": { "issuer": "https://auth.${DOMAIN}/realms/safe", "clientId": "safe-web" },
  "apiBaseUrl": "https://${DOMAIN}/api/v1",
  "wsBaseUrl": "wss://${DOMAIN}/ws/v1",
  "map": {
    "provider": "mapbox",
    "mapboxToken": "${MAPBOX_PUBLIC_TOKEN}",
    "defaultCenter": [${MAP_DEFAULT_CENTER:-12.1,46.45}],
    "defaultZoom": ${MAP_DEFAULT_ZOOM:-11}
  },
  "defaultLocale": "it",
  "supportedLocales": ["it", "en", "de"]
}
JSON

# realm di base: nel repository (../infra) oppure nel clone dei sorgenti sul server (/opt/safe-src)
if [ -z "${REALM_SRC:-}" ]; then
  for f in ../infra/keycloak/realm-safe.json /opt/safe-src/infra/keycloak/realm-safe.json; do
    [ -f "$f" ] && REALM_SRC=$f && break
  done
fi
[ -f "$REALM_SRC" ] || { echo "realm di base non trovato (REALM_SRC)"; exit 1; }
python3 render_realm.py "$REALM_SRC" generated/realm-safe.json

echo "generati: generated/app-config.json, generated/realm-safe.json"
