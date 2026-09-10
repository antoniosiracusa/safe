from __future__ import annotations

from drf_spectacular.utils import extend_schema
from rest_framework import serializers
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from safe.apps.crypto.models import CompanyKey, CompanyKeyGrant, UserKey
from safe.apps.org.models import UserTeam

from .drf import HasPermission
from .resolve import permission_map


class MeResponseSerializer(serializers.Serializer):
    user = serializers.DictField()
    company = serializers.DictField()
    teams = serializers.ListField(child=serializers.DictField())
    permissions = serializers.DictField(child=serializers.BooleanField())
    key_status = serializers.DictField()


class MeView(APIView):
    """Utente corrente, società, squadre e mappa completa dei permessi (docs/03-openapi.yaml /me)."""

    permission_classes = [HasPermission]
    required_permissions: tuple[str, ...] = ()

    @extend_schema(tags=["me"], responses=MeResponseSerializer)
    def get(self, request: Request) -> Response:
        user = request.user
        company = user.company
        teams = [
            {"id": str(ut.team_id), "name": ut.team.name, "is_default": ut.is_default}
            for ut in UserTeam.objects.filter(user=user).select_related("team").order_by("team__name")
        ]
        active_key = CompanyKey.objects.filter(status=CompanyKey.Status.ACTIVE).first()
        has_grant = (
            active_key is not None
            and CompanyKeyGrant.objects.filter(
                user=user, company_key=active_key, revoked_at__isnull=True
            ).exists()
        )
        return Response(
            {
                "user": {
                    "id": str(user.id),
                    "email": user.email,
                    "first_name": user.first_name,
                    "last_name": user.last_name,
                    "locale": user.locale,
                    "mfa_required": user.mfa_required,
                },
                "company": {
                    "id": str(company.id),
                    "name": company.name,
                    "slug": company.slug,
                    "tenant_type": company.tenant_type,
                    "timezone": company.timezone,
                },
                "teams": teams,
                "permissions": permission_map(user),
                "key_status": {
                    "user_key": "present" if UserKey.objects.filter(user=user).exists() else "missing",
                    "company_key_version": active_key.version if active_key else None,
                    "grant": "active" if has_grant else "none",
                },
            }
        )

    @extend_schema(
        tags=["me"], request={"application/json": {"type": "object"}}, responses=MeResponseSerializer
    )
    def patch(self, request: Request) -> Response:
        locale = request.data.get("locale")
        if locale not in ("it", "en", "de"):
            raise serializers.ValidationError({"locale": ["Valore non ammesso."]})
        request.user.locale = locale
        request.user.save(update_fields=["locale", "updated_at"])
        return self.get(request)
