#!/bin/bash
# Da eseguire dopo aver cambiato l'immagine del database (nuova versione correttiva di PostgreSQL/PostGIS o nuova
# base Debian). Idempotente: si può rilanciare senza danni.
#
#   1. reindicizza ogni database: una glibc diversa può ordinare il testo in modo diverso e gli indici sui campi di
#      testo vanno ricostruiti ("collation version mismatch" nei log);
#   2. registra la nuova versione della collation;
#   3. aggiorna l'estensione PostGIS (e le estensioni collegate) alla versione delle librerie installate.
#
#   ./db-post-upgrade.sh                      # produzione (docker-compose.prod.yml + .env)
#   SAFE_DIR=.. COMPOSE="docker compose" ./db-post-upgrade.sh   # sviluppo (compose nella radice del repository)
set -euo pipefail
cd "${SAFE_DIR:-$(dirname "$0")}"
COMPOSE="${COMPOSE:-docker compose --env-file .env -f docker-compose.prod.yml}"
psql_db() { $COMPOSE exec -T db psql -U postgres -v ON_ERROR_STOP=1 -q "$@" </dev/null; }
PSQL=psql_db

echo "versione: $($PSQL -tAc 'select version()' | cut -d' ' -f1-2)"
for db in $($PSQL -tAc "select datname from pg_database where datallowconn order by datname"); do
  echo "== $db"
  $PSQL -d "$db" -c "REINDEX DATABASE \"$db\";" 2>&1 | grep -v "collation version mismatch\|^DETAIL\|^HINT" || true
  $PSQL -d "$db" -c "ALTER DATABASE \"$db\" REFRESH COLLATION VERSION;" 2>&1 | grep -v "collation version mismatch\|^DETAIL\|^HINT\|^NOTICE" || true
  if [ "$($PSQL -d "$db" -tAc "select count(*) from pg_extension where extname='postgis'")" = "1" ]; then
    $PSQL -d "$db" -c "SELECT postgis_extensions_upgrade();" >/dev/null 2>&1 || echo "avviso: aggiornamento PostGIS non riuscito in $db"
    echo "postgis: $($PSQL -d "$db" -tAc "select extversion from pg_extension where extname='postgis'") (librerie $($PSQL -d "$db" -tAc "select postgis_lib_version()"))"
  fi
done
echo "== verifica"
$PSQL -tAc "select datname || ': collation ' || coalesce(datcollversion,'-') || ' / sistema ' || coalesce(pg_database_collation_actual_version(oid),'-') from pg_database where datallowconn order by 1"
