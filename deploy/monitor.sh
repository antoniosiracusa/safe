#!/bin/bash
# Controllo di salute del server (cron ogni ora): disco, container, API, Keycloak, backup recente e
# copia esterna. Invia un'email a ALERT_EMAIL (SMTP di .env) quando compare o sparisce un problema;
# con --report invia sempre un riepilogo (cron settimanale, conferma che gli avvisi funzionano).
#
#   ./monitor.sh            # controlla; email solo se lo stato cambia
#   ./monitor.sh --report   # controlla e invia comunque il riepilogo
#   ./monitor.sh --test     # invia un'email di prova
set -uo pipefail
cd "$(dirname "$0")"
set -a; source ./.env; set +a
MODE="${1:-}"
STATE=/var/lib/safe-monitor.state
problems=(); info=()

use=$(df --output=pcent / | tail -1 | tr -dc 0-9)
info+=("disco usato: ${use}%")
[ "${use:-0}" -ge "${ALERT_DISK_PERCENT:-80}" ] && problems+=("disco al ${use}% (soglia ${ALERT_DISK_PERCENT:-80}%)")

bad=$(docker compose --env-file .env -f docker-compose.prod.yml ps --format '{{.Service}} {{.Status}}' 2>/dev/null \
  | grep -Ei 'unhealthy|exited|restarting|dead' || true)
[ -n "$bad" ] && problems+=("container in errore: $(echo "$bad" | tr '\n' ';')")

# fino a 3 tentativi a distanza di 30 s: un riavvio dell'API (rilascio, migrazioni) dura meno di un minuto
# e non deve generare un falso allarme (successo il 14/09/2026 alle 20:15, durante il rilascio v1.2.0)
health=""
for attempt in 1 2 3; do
  health=$(curl -fsS --max-time 20 "https://${DOMAIN}/api/v1/health" 2>/dev/null || true)
  case "$health" in *'"status":"ok"'*) break ;; esac
  [ "$attempt" -lt 3 ] && sleep 30
done
case "$health" in
  *'"status":"ok"'*) info+=("API ok") ;;
  *) problems+=("l'API non risponde su https://${DOMAIN}/api/v1/health (3 tentativi in 60 s)") ;;
esac
kc=$(curl -s -o /dev/null --max-time 20 -w '%{http_code}' "https://auth.${DOMAIN}/realms/safe" 2>/dev/null || echo 000)
[ "$kc" = "200" ] && info+=("Keycloak ok") || problems+=("Keycloak (accesso utenti) risponde con codice $kc")

days=$(( ( $(date +%s) - $(date -d "$(echo | openssl s_client -connect "${DOMAIN}:443" -servername "${DOMAIN}" 2>/dev/null \
  | openssl x509 -noout -enddate 2>/dev/null | cut -d= -f2)" +%s 2>/dev/null || date +%s) ) / 86400 ))
days=$(( -days ))
[ "$days" -lt 14 ] && problems+=("certificato TLS in scadenza tra $days giorni (rinnovo automatico non avvenuto?)") || info+=("certificato TLS: $days giorni")

last=$(ls -t backups/safe-*.sql.gz.gpg 2>/dev/null | head -1)
if [ -z "$last" ] || [ -n "$(find "$last" -mmin +1560 2>/dev/null)" ]; then
  problems+=("nessun backup nelle ultime 26 ore")
else
  info+=("ultimo backup: $(basename "$last") ($(du -h "$last" | cut -f1))")
  if [ -n "${BACKUP_S3_BUCKET:-}" ] && [ "$(cat backups/.last-uploaded 2>/dev/null)" != "$(basename "$last")" ]; then
    problems+=("l'ultimo backup non risulta copiato sul bucket esterno (vedi /var/log/safe-backup.log)")
  fi
fi

if [ ${#problems[@]} -eq 0 ]; then status="OK"; else status="PROBLEMI"; fi
body="Server ${DOMAIN} - $(date '+%d/%m/%Y %H:%M')"$'\n\n'
if [ ${#problems[@]} -gt 0 ]; then
  body+="PROBLEMI:"$'\n'; for p in "${problems[@]}"; do body+="  - $p"$'\n'; done; body+=$'\n'
fi
body+="Stato:"$'\n'; for i in "${info[@]}"; do body+="  - $i"$'\n'; done
echo "$status: ${problems[*]:-nessun problema}"

send_mail() {  # $1 oggetto, $2 corpo
  python3 - "$1" "$2" <<'PY'
import os, smtplib, ssl, sys
from email.message import EmailMessage
subject, body = sys.argv[1], sys.argv[2]
env = os.environ
m = EmailMessage()
m["From"] = f'{env.get("SMTP_FROM_NAME", "SAFE")} <{env["SMTP_FROM"]}>'
m["To"] = env["ALERT_EMAIL"]
m["Subject"] = subject
m.set_content(body)
host, port = env["SMTP_HOST"], int(env.get("SMTP_PORT", "587"))
if env.get("SMTP_SSL", "false") == "true":
    s = smtplib.SMTP_SSL(host, port, timeout=30, context=ssl.create_default_context())
else:
    s = smtplib.SMTP(host, port, timeout=30)
    if env.get("SMTP_STARTTLS", "true") == "true":
        s.starttls(context=ssl.create_default_context())
if env.get("SMTP_USER"):
    s.login(env["SMTP_USER"], env["SMTP_PASSWORD"])
s.send_message(m)
s.quit()
PY
}

[ -z "${ALERT_EMAIL:-}" ] && { echo "ALERT_EMAIL non impostato: nessuna email"; exit 0; }
prev=$(cat "$STATE" 2>/dev/null || echo "")
printf '%s\n' "${problems[@]}" | sort > "$STATE.new"; cur=$(cat "$STATE.new"); mv "$STATE.new" "$STATE"
case "$MODE" in
  --test)   send_mail "[SAFE] email di prova degli avvisi" "$body" && echo "email di prova inviata a $ALERT_EMAIL" ;;
  --report) send_mail "[SAFE] riepilogo settimanale: $status" "$body" && echo "riepilogo inviato" ;;
  *)
    if [ "$cur" != "$prev" ]; then
      if [ "$status" = "OK" ]; then send_mail "[SAFE] tutto tornato regolare" "$body"
      else send_mail "[SAFE] PROBLEMA sul server" "$body"; fi
      echo "email di avviso inviata a $ALERT_EMAIL"
    fi ;;
esac
