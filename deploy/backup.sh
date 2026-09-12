#!/bin/bash
# Backup notturno: dump del database (SAFE + Keycloak) cifrato con passphrase, conservato in
# /opt/safe/backups per BACKUP_KEEP_DAYS giorni e, se configurato, copiato su un bucket S3 esterno
# (Backblaze B2, Aruba Object Storage, ...) dove resta BACKUP_S3_KEEP_DAYS giorni.
# I file di MinIO (PDF, export) sono rigenerabili e non vengono salvati.
#
# Ripristino: vedi runbook-produzione.md ("Ripristino da backup").
set -euo pipefail
cd "$(dirname "$0")"
set -a; source ./.env; set +a
COMPOSE="docker compose --env-file .env -f docker-compose.prod.yml"
DEST=./backups
mkdir -p "$DEST"
STAMP=$(date +%Y%m%d-%H%M)
OUT="$DEST/safe-$STAMP.sql.gz.gpg"

$COMPOSE exec -T db pg_dumpall -U postgres --clean --if-exists \
  | gzip -6 \
  | gpg --batch --yes --symmetric --cipher-algo AES256 --passphrase "$BACKUP_PASSPHRASE" -o "$OUT"
chmod 600 "$OUT"
echo "backup scritto: $OUT ($(du -h "$OUT" | cut -f1))"

find "$DEST" -name 'safe-*.sql.gz.gpg' -mtime +"${BACKUP_KEEP_DAYS:-30}" -delete

if [ -n "${BACKUP_S3_BUCKET:-}" ]; then
  s3() {
    docker run --rm -v "$PWD/$DEST:/backups:ro" \
      -e AWS_ACCESS_KEY_ID="$BACKUP_S3_ACCESS_KEY" -e AWS_SECRET_ACCESS_KEY="$BACKUP_S3_SECRET_KEY" \
      amazon/aws-cli:2.27.50 s3 "$@" --endpoint-url "$BACKUP_S3_ENDPOINT"
  }
  s3 cp "/backups/$(basename "$OUT")" "s3://$BACKUP_S3_BUCKET/$(basename "$OUT")" --only-show-errors
  echo "copiato su s3://$BACKUP_S3_BUCKET"
  # pulizia remota: i backup più vecchi di BACKUP_S3_KEEP_DAYS giorni (default 90) vengono rimossi.
  # Su Backblaze B2 impostare il ciclo di vita del bucket su "Keep only the last version", altrimenti
  # le versioni nascoste dalla cancellazione restano a consumare spazio.
  CUTOFF=$(date -u -d "-${BACKUP_S3_KEEP_DAYS:-90} days" +%Y-%m-%d)
  s3 ls "s3://$BACKUP_S3_BUCKET/" | while read -r day _ _ name; do
    case "$name" in
      safe-*.sql.gz.gpg) if [[ "$day" < "$CUTOFF" ]]; then s3 rm "s3://$BACKUP_S3_BUCKET/$name" --only-show-errors && echo "rimosso dal bucket: $name"; fi ;;
    esac
  done
fi
