from __future__ import annotations

from django.core.cache import cache
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from safe.apps.authz.drf import HasPermission
from safe.apps.tenancy.context import get_current_company_id

from .models import DIMENSIONS, Country, LookupValue


def lookups_payload(dimension: str | None = None) -> dict:
    qs = LookupValue.objects.active_for_tenant().select_related("parent")
    if dimension:
        qs = qs.filter(dimension=dimension)
    out: dict[str, list[dict]] = {d: [] for d in (DIMENSIONS if not dimension else [dimension])}
    for v in qs.order_by("dimension", "sort_order", "code"):
        out[v.dimension].append(
            {
                "id": str(v.id),
                "code": v.code,
                "labels": v.labels,
                "sort_order": v.sort_order,
                "is_custom": v.company_id is not None,
                "parent": v.parent.code if v.parent else None,
                "color": v.color or None,
                "mapping": v.mapping,
            }
        )
    if not dimension:
        out["country"] = [
            {"code": c.code, "labels": {"it": c.name_it, "en": c.name_en, "de": c.name_de}, "is_eu": c.is_eu}
            for c in Country.objects.all()
        ]
    return out


class LookupsView(APIView):
    """Tutti i vocabolari attivi per la società, in tutte le lingue (form e grafici)."""

    permission_classes = [HasPermission]
    required_permissions: tuple[str, ...] = ()

    @extend_schema(
        tags=["lookups"],
        parameters=[OpenApiParameter("dimension", str, required=False)],
        responses={200: {"type": "object"}},
    )
    def get(self, request: Request) -> Response:
        dimension = request.query_params.get("dimension")
        if dimension and dimension not in DIMENSIONS:
            return Response(
                {"code": "unknown_dimension", "detail": f"Dimensione '{dimension}' sconosciuta."}, 400
            )
        key = f"lookups:{get_current_company_id()}:{dimension or 'all'}"
        payload = cache.get(key)
        if payload is None:
            payload = lookups_payload(dimension)
            cache.set(key, payload, 300)
        return Response(payload)
