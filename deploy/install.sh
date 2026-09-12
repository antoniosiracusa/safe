#!/bin/bash
# Prima installazione sul server (Ubuntu 24.04 con Docker già presente). Da eseguire come root:
#
#   git clone https://github.com/antoniosiracusa/safe.git /opt/safe-src   (oppure copia della cartella deploy/)
#   cp -r /opt/safe-src/deploy /opt/safe && cd /opt/safe && cp .env.production.example .env
#   nano .env        # dominio, segreti, SMTP, token Mapbox
#   ./install.sh
set -euo pipefail
cd "$(dirname "$0")"
apt-get install -y -qq gnupg gettext-base >/dev/null
chmod +x ./*.sh ./db/init.prod.sh
grep -q CHANGE-ME .env && { echo "ERRORE: in .env restano valori CHANGE-ME"; exit 1; }
./deploy.sh
# backup notturno alle 02:30 e pulizia settimanale delle immagini non usate
( crontab -l 2>/dev/null | grep -v 'safe/backup.sh' ; echo "30 2 * * * cd /opt/safe && ./backup.sh >> /var/log/safe-backup.log 2>&1" ) | crontab -
( crontab -l 2>/dev/null | grep -v 'docker image prune' ; echo "0 4 * * 0 docker image prune -af >/dev/null 2>&1" ) | crontab -
# controllo di salute ogni ora (email solo se cambia lo stato) e riepilogo il lunedì alle 08:00
( crontab -l 2>/dev/null | grep -v 'safe/monitor.sh' ; echo "15 * * * * cd /opt/safe && ./monitor.sh >> /var/log/safe-monitor.log 2>&1"; echo "0 8 * * 1 cd /opt/safe && ./monitor.sh --report >> /var/log/safe-monitor.log 2>&1" ) | crontab -
echo "installazione completata; cron attivi: backup 02:30, monitor ogni ora, riepilogo lunedì 08:00"
echo "consigliato ora: ./restore-test.sh (prova di ripristino) e ./monitor.sh --test (email di prova)"
