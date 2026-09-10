"""Integrazione DRF: l'autenticazione è già avvenuta nel TenantMiddleware."""

from __future__ import annotations

from rest_framework import exceptions
from rest_framework.authentication import BaseAuthentication
from rest_framework.request import Request


class OIDCAuthentication(BaseAuthentication):
    def authenticate(self, request: Request):  # noqa: ANN201
        http = request._request  # noqa: SLF001
        error = getattr(http, "auth_error", None)
        if error is not None:
            raise exceptions.AuthenticationFailed({"detail": error.detail, "code": error.code})
        user = getattr(http, "user", None)
        if user is None or not user.is_authenticated:
            return None
        return (user, None)

    def authenticate_header(self, request: Request) -> str:
        return 'Bearer realm="safe"'
