from django.conf import settings
from django.db import connection
from drf_spectacular.utils import extend_schema
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView


class HealthView(APIView):
    """Liveness/readiness per orchestratore e CI. Nessun dato applicativo."""

    permission_classes = [AllowAny]
    authentication_classes: list = []

    @extend_schema(tags=["meta"], responses={200: {"type": "object"}})
    def get(self, request: Request) -> Response:
        with connection.cursor() as cur:
            cur.execute("SELECT postgis_version()")
            postgis = cur.fetchone()[0]
        return Response(
            {
                "status": "ok",
                "version": "0.1.0",
                "database": "ok",
                "postgis": postgis.split(" ")[0],
                "oidc_issuer": settings.OIDC_ISSUER,
            }
        )
