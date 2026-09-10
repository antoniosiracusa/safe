from __future__ import annotations

from typing import Any

from safe.apps.tenancy.context import get_current_company_id

from .models import AuditLog


def record(
    action: str,
    object_type: str,
    *,
    object_id: Any = None,
    event_id: Any = None,
    actor: Any = None,
    request: Any = None,
    changed_fields: list[str] | None = None,
    metadata: dict[str, Any] | None = None,
) -> AuditLog:
    company_id = get_current_company_id()
    if company_id is None and actor is not None:
        company_id = actor.company_id
    ip = None
    user_agent = ""
    if request is not None:
        forwarded = request.META.get("HTTP_X_FORWARDED_FOR")
        ip = (forwarded.split(",")[0].strip() if forwarded else request.META.get("REMOTE_ADDR")) or None
        user_agent = request.META.get("HTTP_USER_AGENT", "")[:300]
        if actor is None and getattr(request, "user", None) is not None and request.user.is_authenticated:
            actor = request.user
    return AuditLog.all_objects.create(
        company_id=company_id,
        actor_user_id=getattr(actor, "id", None),
        action=action,
        object_type=object_type,
        object_id=object_id,
        event_id=event_id,
        changed_fields=changed_fields or [],
        metadata=metadata or {},
        ip=ip,
        user_agent=user_agent,
    )
