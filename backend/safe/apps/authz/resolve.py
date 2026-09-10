"""Risoluzione dei permessi effettivi: ⋃ ruoli ∪ grant − deny, più i permessi derivati."""

from __future__ import annotations

from django.core.cache import cache

from .catalog import ALL_CODES, DERIVED_CODES
from .models import RolePermission, UserPermission

CACHE_SECONDS = 60


def cache_key(user_id: object) -> str:
    return f"authz:perms:{user_id}"


def invalidate(user_id: object) -> None:
    cache.delete(cache_key(user_id))


def effective_permissions(user) -> frozenset[str]:  # noqa: ANN001
    key = cache_key(user.id)
    cached = cache.get(key)
    if cached is not None:
        return frozenset(cached)

    from_roles = set(
        RolePermission.objects.filter(role__user_roles__user_id=user.id).values_list(
            "permission_id", flat=True
        )
    )
    direct = UserPermission.objects.filter(user_id=user.id).values_list("permission_id", "effect")
    grants = {code for code, effect in direct if effect == UserPermission.Effect.GRANT}
    denies = {code for code, effect in direct if effect == UserPermission.Effect.DENY}
    perms = (from_roles | grants) - denies
    if user.is_platform_admin:
        perms.add("platform.admin")

    # derivati
    from safe.apps.crypto.models import CompanyKeyGrant

    if CompanyKeyGrant.objects.filter(
        user_id=user.id, revoked_at__isnull=True, company_key__status="active"
    ).exists():
        perms.add("crypto.holder")

    cache.set(key, sorted(perms), CACHE_SECONDS)
    return frozenset(perms)


def permission_map(user) -> dict[str, bool]:  # noqa: ANN001
    perms = effective_permissions(user)
    return {code: code in perms for code in (*ALL_CODES, *DERIVED_CODES)}
