# Loghi della pagina di accesso

Salvare qui i due file PNG (sfondo trasparente o bianco, altezza consigliata 300-400 px):

- `ski-civetta.png` — logo Ski Civetta (a sinistra)
- `civetta-superbike.png` — logo Civetta Superbike (a destra)

Il tema (`../css/safe.css`) li mostra in un riquadro bianco sopra il titolo della pagina, che è il
`displayName` del realm (`REALM_DISPLAY_NAME` in `.env`). Dopo aver aggiunto o cambiato i file:
`./deploy.sh` (Keycloak in produzione tiene i temi in cache: il riavvio del servizio li ricarica).
