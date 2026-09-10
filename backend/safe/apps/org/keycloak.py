"""Client minimo per la Keycloak Admin REST API (client `safe-admin`, credenziali di servizio).

L'app non gestisce mai password: crea l'utente in Keycloak e gli invia l'email "imposta password"
(più "configura OTP" se la società richiede MFA). Disattivazione = utente disabilitato + sessioni revocate.
In test viene sostituito da un fake (`get_client` è il punto di monkeypatch).
"""

from __future__ import annotations

import logging
import time
from typing import Any

import requests
from django.conf import settings

log = logging.getLogger(__name__)


class KeycloakError(Exception):
    def __init__(self, code: str, detail: str, status: int = 502) -> None:
        super().__init__(detail)
        self.code = code
        self.detail = detail
        self.status = status


class KeycloakAdmin:
    def __init__(self) -> None:
        self.base = settings.KEYCLOAK_ADMIN_URL.rstrip("/")
        self.realm = settings.KEYCLOAK_REALM
        self._token: str | None = None
        self._token_exp = 0.0

    # --- autenticazione ---------------------------------------------------------------
    def _auth(self) -> str:
        if self._token and time.time() < self._token_exp - 10:
            return self._token
        r = requests.post(
            f"{self.base}/realms/{self.realm}/protocol/openid-connect/token",
            data={
                "grant_type": "client_credentials",
                "client_id": settings.KEYCLOAK_ADMIN_CLIENT_ID,
                "client_secret": settings.KEYCLOAK_ADMIN_CLIENT_SECRET,
            },
            timeout=10,
        )
        if r.status_code != 200:
            raise KeycloakError("keycloak_auth", "Autenticazione al server di identità non riuscita.")
        body = r.json()
        self._token = body["access_token"]
        self._token_exp = time.time() + int(body.get("expires_in", 60))
        return self._token

    def _req(self, method: str, path: str, **kw: Any) -> requests.Response:
        headers = {"Authorization": f"Bearer {self._auth()}"}
        r = requests.request(
            method, f"{self.base}/admin/realms/{self.realm}{path}", headers=headers, timeout=15, **kw
        )
        if r.status_code >= 500:
            log.error("keycloak %s %s → %s %s", method, path, r.status_code, r.text[:300])
            raise KeycloakError("keycloak_unavailable", "Server di identità non disponibile.")
        return r

    # --- utenti -----------------------------------------------------------------------
    def find_user_by_email(self, email: str) -> dict[str, Any] | None:
        r = self._req("GET", "/users", params={"email": email, "exact": "true"})
        users = r.json() if r.status_code == 200 else []
        return next((u for u in users if (u.get("email") or "").lower() == email.lower()), None)

    def create_user(self, *, email: str, first_name: str, last_name: str, locale: str) -> str:
        """Crea l'utente (abilitato, senza password) e ne restituisce l'id; se esiste già lo riusa."""
        payload = {
            "username": email,
            "email": email,
            "firstName": first_name,
            "lastName": last_name,
            "enabled": True,
            "emailVerified": False,
            "attributes": {"locale": [locale]},
        }
        r = self._req("POST", "/users", json=payload)
        if r.status_code == 201:
            return r.headers["Location"].rstrip("/").rsplit("/", 1)[-1]
        if r.status_code == 409:
            existing = self.find_user_by_email(email)
            if existing:
                return str(existing["id"])
        raise KeycloakError("keycloak_create_failed", f"Creazione utente non riuscita ({r.status_code}).")

    def update_user(self, kc_id: str, **fields: Any) -> None:
        payload: dict[str, Any] = {}
        if "first_name" in fields:
            payload["firstName"] = fields["first_name"]
        if "last_name" in fields:
            payload["lastName"] = fields["last_name"]
        if "locale" in fields:
            payload["attributes"] = {"locale": [fields["locale"]]}
        if "enabled" in fields:
            payload["enabled"] = fields["enabled"]
        if payload:
            r = self._req("PUT", f"/users/{kc_id}", json=payload)
            if r.status_code not in (204, 200):
                raise KeycloakError(
                    "keycloak_update_failed", f"Aggiornamento utente non riuscito ({r.status_code})."
                )

    def send_actions_email(self, kc_id: str, *, actions: list[str], redirect_uri: str, lifespan: int) -> None:
        r = self._req(
            "PUT",
            f"/users/{kc_id}/execute-actions-email",
            params={
                "client_id": settings.KEYCLOAK_WEB_CLIENT_ID,
                "redirect_uri": redirect_uri,
                "lifespan": lifespan,
            },
            json=actions,
        )
        if r.status_code not in (204, 200):
            raise KeycloakError("keycloak_email_failed", f"Invio email non riuscito ({r.status_code}).")

    def logout_user(self, kc_id: str) -> None:
        self._req("POST", f"/users/{kc_id}/logout")

    def set_enabled(self, kc_id: str, enabled: bool) -> None:
        self.update_user(kc_id, enabled=enabled)
        if not enabled:
            self.logout_user(kc_id)


_client: KeycloakAdmin | None = None


def get_client() -> KeycloakAdmin:
    global _client
    if _client is None:
        _client = KeycloakAdmin()
    return _client


def invite_actions(mfa_required: bool) -> list[str]:
    actions = ["UPDATE_PASSWORD"]
    if mfa_required:
        actions.append("CONFIGURE_TOTP")
    return actions
