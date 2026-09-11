"""Hardening HTTP (docs/07-dpia §3): security header su ogni risposta, nessuna cache per l'API,
e divieto di dati personali nella query string (mai in URL né nei log degli accessi)."""

from __future__ import annotations

from collections.abc import Callable

from django.http import HttpRequest, HttpResponse, JsonResponse

PII_QUERY_PARAMS = frozenset(
    {
        "firstname",
        "first_name",
        "surname",
        "last_name",
        "lastname",
        "name",
        "nome",
        "cognome",
        "email",
        "phone",
        "telefono",
        "birth_date",
        "birthdate",
        "fiscal_code",
        "codice_fiscale",
        "address",
        "indirizzo",
    }
)


class SecurityHeadersMiddleware:
    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        is_api = request.path.startswith("/api/v1/")
        if is_api:
            bad = PII_QUERY_PARAMS.intersection(k.lower() for k in request.GET)
            if bad:
                return JsonResponse(
                    {
                        "code": "pii_in_url",
                        "detail": "Dati personali non ammessi nella URL.",
                        "fields": {k: ["non ammesso"] for k in sorted(bad)},
                    },
                    status=400,
                )
        response = self.get_response(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        response.headers.setdefault("Permissions-Policy", "geolocation=(), camera=(), microphone=()")
        response.headers.setdefault("X-Frame-Options", "DENY")
        if is_api:
            response.headers.setdefault(
                "Content-Security-Policy", "default-src 'none'; frame-ancestors 'none'"
            )
            response.headers.setdefault("Cache-Control", "no-store")
        return response
