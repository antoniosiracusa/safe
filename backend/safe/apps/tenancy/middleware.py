"""Autenticazione OIDC + contesto tenant per ogni richiesta HTTP.

Ordine: il token Bearer viene validato qui (JWKS dell'issuer), l'utente viene caricato dal DB
applicativo e il tenant deriva dall'utente. Tutta la richiesta gira in una transazione con
`SET LOCAL app.company_id`, così ORM e RLS lavorano sullo stesso tenant.
"""

from __future__ import annotations

import logging
from collections.abc import Callable

from django.contrib.auth.models import AnonymousUser
from django.http import HttpRequest, HttpResponse

from safe.apps.authn.jwt import AuthError, authenticate_bearer

from .context import tenant_context

log = logging.getLogger(__name__)


class TenantMiddleware:
    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        request.user = AnonymousUser()
        request.auth_error = None  # type: ignore[attr-defined]
        request.tenant = None  # type: ignore[attr-defined]

        header = request.META.get("HTTP_AUTHORIZATION", "")
        if header.lower().startswith("bearer "):
            try:
                user = authenticate_bearer(header[7:].strip())
            except AuthError as exc:
                request.auth_error = exc  # type: ignore[attr-defined]
            else:
                request.user = user
                request.tenant = user.company  # type: ignore[attr-defined]

        if request.tenant is not None:  # type: ignore[attr-defined]
            with tenant_context(request.tenant.id):  # type: ignore[attr-defined]
                return self.get_response(request)
        return self.get_response(request)
