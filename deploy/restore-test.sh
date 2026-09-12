#!/bin/bash
# Prova di ripristino: decifra l'ultimo backup (o il file indicato) e lo carica in un PostgreSQL
# temporaneo, separato da quello in esercizio; stampa i conteggi principali e rimuove tutto.
# Da eseguire dopo l'installazione e almeno una volta l'anno (checklist go-live, docs/08-messa-online.md).
#
#   ./restore-test.sh                                  # ultimo backup in ./backups
#   ./restore-test.sh backups/safe-20260912-1216.sql.gz.gpg
set -euo pipefail
cd "$(dirname "$0")"
set -a; source ./.env; set +a
FILE="${1:-$(ls -t backups/safe-*.sql.gz.gpg | head -1)}"
NAME=safe-restore-test
LOG=/tmp/safe-restore-test.log
IMAGE=$(docker compose --env-file .env -f docker-compose.prod.yml config --images 2>/dev/null | grep postgis || echo postgis/postgis:16-3.4)

docker rm -f "$NAME" >/dev/null 2>&1 || true
docker run -d --name "$NAME" -e POSTGRES_PASSWORD=restore-test "$IMAGE" >/dev/null
# l'immagine avvia un server provvisorio per l'inizializzazione e poi quello definitivo: attendere il secondo
for _ in $(seq 1 60); do
  docker logs "$NAME" 2>&1 | grep -q "PostgreSQL init process complete"     && docker exec "$NAME" pg_isready -U postgres -q 2>/dev/null && break
  sleep 2
done

echo "ripristino di $FILE in un PostgreSQL temporaneo..."
# search_path=public: i backup precedenti alla migrazione tenancy.0003 hanno una funzione di CHECK che cerca
# lookup_value senza schema e con il search_path vuoto del dump i COPY fallirebbero
gpg --batch --quiet --decrypt --passphrase "$BACKUP_PASSPHRASE" "$FILE" | gunzip \
  | sed "s/^SELECT pg_catalog.set_config('search_path', '', false);/SELECT pg_catalog.set_config('search_path', 'public', false);/" \
  | docker exec -i "$NAME" psql -U postgres -q -d postgres >"$LOG" 2>&1 || true
# errori attesi con --clean su un cluster nuovo: template1/ruolo postgres non eliminabili, oggetti PostGIS già creati dall'immagine
unexpected=$(grep -E '^(ERROR|FATAL)' "$LOG" | grep -vE 'role "postgres" already exists|cannot drop a template database|current user cannot be dropped|"template_postgis" already exists|schema "(tiger|tiger_data|topology)" already exists' || true)
if [ -n "$unexpected" ]; then
  echo "ERRORI durante il ripristino:"; echo "$unexpected" | head -10
  docker rm -f "$NAME" >/dev/null; exit 1
fi

echo "conteggi nel database ripristinato:"
docker exec "$NAME" psql -U postgres -d safe -Atc "
  select 'società: '||count(*) from company union all
  select 'utenti: '||count(*) from app_user union all
  select 'eventi: '||count(*) from event union all
  select 'persone: '||count(*) from person union all
  select 'zone: '||count(*) from zone union all
  select 'piste: '||count(*) from slope union all
  select 'confini ISTAT: '||count(*) from istat_admin_unit union all
  select 'audit: '||count(*) from audit_log" | sed 's/^/  /'
docker exec "$NAME" psql -U postgres -d keycloak -Atc "select 'utenti Keycloak: '||count(*) from user_entity" | sed 's/^/  /'
docker rm -f "$NAME" >/dev/null
echo "prova di ripristino riuscita; container temporaneo rimosso"
