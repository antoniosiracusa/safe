"""Formato errori uniforme: {"code": ..., "detail": ..., "fields": {...}, "missing": [...]}."""

from typing import Any

from rest_framework import exceptions, status
from rest_framework.response import Response
from rest_framework.views import exception_handler as drf_exception_handler

_CODES = {
    status.HTTP_400_BAD_REQUEST: "validation_error",
    status.HTTP_401_UNAUTHORIZED: "not_authenticated",
    status.HTTP_403_FORBIDDEN: "permission_denied",
    status.HTTP_404_NOT_FOUND: "not_found",
    status.HTTP_405_METHOD_NOT_ALLOWED: "method_not_allowed",
    status.HTTP_409_CONFLICT: "conflict",
    status.HTTP_429_TOO_MANY_REQUESTS: "throttled",
}


class BusinessError(exceptions.APIException):
    """Errore di dominio con codice esplicito: {"code": ..., "detail": ...} (400 di default)."""

    status_code: int = status.HTTP_400_BAD_REQUEST

    def __init__(self, code: str, detail: str, status_code: int | None = None) -> None:
        if status_code is not None:
            self.status_code = status_code
        super().__init__({"detail": detail, "code": code})


class ConflictError(exceptions.APIException):
    status_code = status.HTTP_409_CONFLICT
    default_detail = "Conflitto con lo stato corrente della risorsa."
    default_code = "conflict"


def exception_handler(exc: Exception, context: dict[str, Any]) -> Response | None:
    response = drf_exception_handler(exc, context)
    if response is None:
        return None

    body: dict[str, Any] = {"code": _CODES.get(response.status_code, "error")}
    if isinstance(exc, exceptions.ValidationError):
        body["detail"] = "Dati non validi."
        data = response.data
        body["fields"] = data if isinstance(data, dict) else {"non_field_errors": data}
    elif isinstance(response.data, dict):
        body["detail"] = str(response.data.get("detail", exc))
        for extra in ("missing", "code"):
            if extra in response.data and extra not in body:
                body[extra] = response.data[extra]
        if "code" in response.data:
            body["code"] = response.data["code"]
    else:
        body["detail"] = str(exc)

    response.data = body
    return response
