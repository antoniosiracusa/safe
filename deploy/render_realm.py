"""Deriva il realm Keycloak di produzione da quello di sviluppo (infra/keycloak/realm-safe.json):
niente utenti demo né client `safe-dev-cli`, redirect sul dominio pubblico, SMTP reale, secret del
client admin, politiche di sicurezza. Le variabili arrivano da .env (esportate da render.sh).

    python3 render_realm.py ../infra/keycloak/realm-safe.json generated/realm-safe.json
"""

from __future__ import annotations

import json
import os
import sys

src, dst = sys.argv[1], sys.argv[2]
env = os.environ
domain = env["DOMAIN"]
web = f"https://{domain}"

realm = json.load(open(src, encoding="utf-8"))

realm["displayName"] = env.get("REALM_DISPLAY_NAME", "SAFE")
realm["displayNameHtml"] = env.get("REALM_DISPLAY_NAME", "SAFE")
realm["loginTheme"] = "safe"  # deploy/keycloak/themes/safe (titolo e loghi della società)
realm["sslRequired"] = "external"
realm["bruteForceProtected"] = True
realm["failureFactor"] = 8
realm["waitIncrementSeconds"] = 60
realm["maxFailureWaitSeconds"] = 900
realm["passwordPolicy"] = "length(12) and notUsername and notEmail and passwordHistory(3)"
realm["accessTokenLifespan"] = 900
realm["ssoSessionIdleTimeout"] = 1800
realm["ssoSessionMaxLifespan"] = 36000
realm["loginWithEmailAllowed"] = True
realm["registrationAllowed"] = False
realm["resetPasswordAllowed"] = True
realm["rememberMe"] = False
realm["smtpServer"] = {
    "host": env["SMTP_HOST"],
    "port": env.get("SMTP_PORT", "587"),
    "from": env["SMTP_FROM"],
    "fromDisplayName": env.get("SMTP_FROM_NAME", "SAFE"),
    "auth": "true" if env.get("SMTP_USER") else "false",
    "user": env.get("SMTP_USER", ""),
    "password": env.get("SMTP_PASSWORD", ""),
    "ssl": env.get("SMTP_SSL", "false"),
    "starttls": env.get("SMTP_STARTTLS", "true"),
}

clients = []
for c in realm["clients"]:
    cid = c["clientId"]
    if cid == "safe-dev-cli":
        continue  # password grant: solo sviluppo
    if cid == "safe-web":
        c["rootUrl"] = web
        c["baseUrl"] = "/"
        c["redirectUris"] = [f"{web}/*"]
        c["webOrigins"] = [web]
        c["attributes"] = {**c.get("attributes", {}), "post.logout.redirect.uris": f"{web}/*", "pkce.code.challenge.method": "S256"}
    if cid == "safe-admin":
        c["secret"] = env["KEYCLOAK_ADMIN_CLIENT_SECRET"]
    if cid == "safe-mobile":
        c["redirectUris"] = ["safe://auth/callback"]
    c["directAccessGrantsEnabled"] = False
    clients.append(c)
realm["clients"] = clients

# solo il service account del client admin; nessun utente demo
realm["users"] = [u for u in realm.get("users", []) if u["username"].startswith("service-account-")]

json.dump(realm, open(dst, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
print(f"realm di produzione scritto in {dst} ({len(clients)} client, {len(realm['users'])} utenti tecnici)")
