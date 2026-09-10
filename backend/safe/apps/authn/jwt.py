"""Validazione dei JWT emessi dall'identity provider OIDC (Keycloak).

- Le chiavi pubbliche arrivano dal JWKS dell'issuer (cache in memoria + Redis, 1 h).
- Si verificano firma, `iss`, `aud`, `exp`, `nbf`. Il token contiene solo `sub`, `email`,
  `preferred_username`: ruoli e permessi vivono nel DB applicativo.
- L'utente viene risolto per `oidc_subject`; al primo accesso di un invitato (riga con lo stesso
  email e `status=invited`) il `sub` viene agganciato e lo stato passa ad `active`.
"""

from __future__ import annotations

import logging
from typing import Any

import jwt
import requests
from django.conf import settings
from django.core.cache import cache
from django.utils import timezone
from jwt import PyJWK, PyJWKClient

from safe.apps.tenancy.context import bypass_tenant

log = logging.getLogger(__name__)


class AuthError(Exception):
    def __init__(self, code: str, detail: str) -> None:
        super().__init__(detail)
        self.code = code
        self.detail = detail


_jwks_client: PyJWKClient | None = None


def _jwks() -> PyJWKClient:
    global _jwks_client
    if _jwks_client is None:
        _jwks_client = PyJWKClient(
            settings.OIDC_JWKS_URL,
            cache_keys=True,
            lifespan=settings.OIDC_JWKS_CACHE_SECONDS,
        )
    return _jwks_client


def _signing_key(token: str) -> PyJWK:
    try:
        return _jwks().get_signing_key_from_jwt(token)
    except jwt.PyJWKClientError as exc:
        raise AuthError("invalid_token", "Chiave di firma non riconosciuta.") from exc
    except requests.RequestException as exc:  # pragma: no cover - dipende dalla rete
        log.warning("JWKS non raggiungibile: %s", exc)
        raise AuthError("idp_unavailable", "Identity provider non raggiungibile.") from exc


def decode_token(token: str) -> dict[str, Any]:
    try:
        key = _signing_key(token)
        return jwt.decode(
            token,
            key.key,
            algorithms=["RS256", "ES256"],
            audience=settings.OIDC_AUDIENCE,
            issuer=settings.OIDC_ISSUER,
            options={"require": ["exp", "iat", "sub"]},
            leeway=30,
        )
    except jwt.ExpiredSignatureError as exc:
        raise AuthError("token_expired", "Token scaduto.") from exc
    except jwt.InvalidAudienceError as exc:
        raise AuthError("invalid_audience", "Token non destinato a questa API.") from exc
    except jwt.InvalidIssuerError as exc:
        raise AuthError("invalid_issuer", "Issuer non riconosciuto.") from exc
    except jwt.PyJWTError as exc:
        raise AuthError("invalid_token", "Token non valido.") from exc


def resolve_user(claims: dict[str, Any]):  # noqa: ANN201 - evita import circolare del modello
    from safe.apps.org.models import AppUser

    sub = claims["sub"]
    email = (claims.get("email") or "").lower()
    cache_key = f"authn:user:{sub}"
    user_id = cache.get(cache_key)

    # La risoluzione avviene fuori dal tenant (non lo conosciamo ancora): bypass esplicito.
    with bypass_tenant():
        user = None
        if user_id:
            user = AppUser.all_objects.select_related("company").filter(id=user_id).first()
        if user is None:
            user = AppUser.all_objects.select_related("company").filter(oidc_subject=sub).first()
        if user is None and email:
            invited = (
                AppUser.all_objects.select_related("company")
                .filter(email=email, oidc_subject__isnull=True, status=AppUser.Status.INVITED)
                .first()
            )
            if invited is not None:
                invited.oidc_subject = sub
                invited.status = AppUser.Status.ACTIVE
                invited.activated_at = timezone.now()
                invited.save(update_fields=["oidc_subject", "status", "activated_at", "updated_at"])
                user = invited
        if user is None:
            raise AuthError("user_not_provisioned", "L'utente non è stato invitato in alcuna società.")
        if user.status != AppUser.Status.ACTIVE or not user.company.is_active:
            raise AuthError("user_disabled", "Utente disattivato.")
        if user.last_login_at is None or (timezone.now() - user.last_login_at).total_seconds() > 300:
            user.last_login_at = timezone.now()
            user.save(update_fields=["last_login_at"])

    cache.set(cache_key, user.id, 300)
    return user


def authenticate_bearer(token: str):  # noqa: ANN201
    claims = decode_token(token)
    return resolve_user(claims)
