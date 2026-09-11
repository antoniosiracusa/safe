#!/bin/bash
# Backup notturno: dump del database (SAFE + Keycloak) cifrato con passphrase, conservato in
# /opt/safe/backups per BACKUP_KEEP_DAYS giorni e, se configurato, copiato su un bucket S3 esterno
# (Aruba Object Storage). I file di MinIO (PDF, export) sono rigenerabili e non vengono salvati.
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
  docker run --rm -v "$PWD/$DEST:/backups:ro" \
    -e AWS_ACCESS_KEY_ID="$BACKUP_S3_ACCESS_KEY" -e AWS_SECRET_ACCESS_KEY="$BACKUP_S3_SECRET_KEY" \
    amazon/aws-cli:2.27.50 s3 cp "/backups/$(basename "$OUT")" "s3://$BACKUP_S3_BUCKET/$(basename "$OUT")" \
    --endpoint-url "$BACKUP_S3_ENDPOINT" --only-show-errors
  echo "copiato su s3://$BACKUP_S3_BUCKET"
fi
