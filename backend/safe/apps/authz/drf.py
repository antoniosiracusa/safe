"""Permission class DRF: ogni vista dichiara `required_permissions` (tutti richiesti) oppure
`permission_map = {"list": (...), "create": (...)}` per ViewSet con permessi diversi per azione.

Senza permesso: 403 {"code":"permission_denied","missing":[...]} e nessun dato.
"""

from __future__ import annotations

from rest_framework import exceptions, permissions
from rest_framework.request import Request

from .resolve import effective_permissions


class PermissionDenied(exceptions.PermissionDenied):
    def __init__(self, missing: list[str]) -> None:
        super().__init__(
            {
                "detail": "Funzione non abilitata per il tuo profilo.",
                "code": "permission_denied",
                "missing": missing,
            }
        )


def required_for(view, request: Request) -> tuple[str, ...]:  # noqa: ANN001
    action = getattr(view, "action", None)
    mapping = getattr(view, "permission_map", None)
    if mapping is not None and action is not None:
        return tuple(mapping.get(action, mapping.get("*", ())))
    if mapping is not None:
        return tuple(mapping.get(request.method.lower(), mapping.get("*", ())))
    return tuple(getattr(view, "required_permissions", ()))


class HasPermission(permissions.BasePermission):
    def has_permission(self, request: Request, view) -> bool:  # noqa: ANN001
        if not request.user or not request.user.is_authenticated:
            raise exceptions.NotAuthenticated()
        required = required_for(view, request)
        if not required:
            return True
        have = effective_permissions(request.user)
        missing = [code for code in required if code not in have]
        if missing:
            raise PermissionDenied(missing)
        return True
