"""Dispositivi mobili: codice di registrazione (QR), registrazione dall'app, autorizzazione, revoca."""

from __future__ import annotations

import base64
import hashlib
import io
import json
import secrets
from datetime import timedelta
from typing import Any, cast

from django.conf import settings
from django.db.models import QuerySet
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django_filters import rest_framework as df
from drf_spectacular.utils import extend_schema
from rest_framework import mixins, serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from safe.apps.audit import service as audit
from safe.apps.authz.drf import HasPermission
from safe.apps.core.exceptions import BusinessError
from safe.apps.org.models import AppUser

from .models import DeviceEnrollmentCode, MobileDevice

CODE_TTL_MINUTES = 15


def _hash(code: str) -> str:
    return hashlib.sha256(code.encode()).hexdigest()


def qr_svg_data_uri(payload: str) -> str:
    import qrcode
    from qrcode.image.svg import SvgPathImage

    img = qrcode.make(payload, image_factory=SvgPathImage, box_size=12, border=2)
    buf = io.BytesIO()
    img.save(buf)
    return "data:image/svg+xml;base64," + base64.b64encode(buf.getvalue()).decode()


class DeviceSerializer(serializers.ModelSerializer):
    user = serializers.SerializerMethodField()

    class Meta:
        model = MobileDevice
        fields = [
            "id",
            "name",
            "user",
            "platform",
            "os_version",
            "app_version",
            "status",
            "enrolled_at",
            "authorized_at",
            "last_seen_at",
            "revoked_at",
        ]

    def get_user(self, d: MobileDevice) -> dict:
        return {"id": str(d.user_id), "email": d.user.email, "name": d.user.full_name}


class DeviceFilter(df.FilterSet):
    status = df.CharFilter(field_name="status")
    user = df.UUIDFilter(field_name="user_id")


class DeviceViewSet(
    mixins.ListModelMixin, mixins.UpdateModelMixin, mixins.DestroyModelMixin, viewsets.GenericViewSet
):
    permission_classes = [HasPermission]
    permission_map = {
        "list": ("devices.view",),
        "partial_update": ("devices.manage",),
        "destroy": ("devices.manage",),
        "authorize": ("devices.authorize",),
        "enrollment_code": ("devices.manage",),
        "register": (),
        "heartbeat": (),
    }
    serializer_class = DeviceSerializer
    filterset_class = DeviceFilter
    pagination_class = None
    http_method_names = ["get", "post", "patch", "delete", "head", "options"]

    def get_queryset(self) -> QuerySet:
        return MobileDevice.objects.select_related("user").order_by("-enrolled_at")

    def partial_update(self, request: Request, pk: str) -> Response:
        device = get_object_or_404(self.get_queryset(), pk=pk)
        name = str(cast(dict[str, Any], request.data).get("name", "")).strip()
        if not name:
            raise serializers.ValidationError({"name": ["Obbligatorio."]})
        device.name = name[:120]
        device.save(update_fields=["name", "updated_at"])
        return Response(DeviceSerializer(device).data)

    def perform_destroy(self, instance: MobileDevice) -> None:
        """Revoca (il record resta per lo storico)."""
        if instance.status != MobileDevice.Status.REVOKED:
            instance.status = MobileDevice.Status.REVOKED
            instance.revoked_at = timezone.now()
            instance.save(update_fields=["status", "revoked_at", "updated_at"])
            audit.record("device.revoke", "device", object_id=instance.id, request=self.request)

    @action(detail=True, methods=["post"])
    def authorize(self, request: Request, pk: str) -> Response:
        device = get_object_or_404(self.get_queryset(), pk=pk)
        if device.status == MobileDevice.Status.REVOKED:
            raise BusinessError("device_revoked", "Dispositivo revocato.")
        if device.status != MobileDevice.Status.AUTHORIZED:
            device.status = MobileDevice.Status.AUTHORIZED
            device.authorized_at = timezone.now()
            device.authorized_by = cast(AppUser, request.user)
            device.save(update_fields=["status", "authorized_at", "authorized_by", "updated_at"])
            audit.record("device.authorize", "device", object_id=device.id, request=request)
        return Response(DeviceSerializer(device).data)

    @extend_schema(responses={201: {"type": "object"}})
    @action(detail=False, methods=["post"], url_path="enrollment-code")
    def enrollment_code(self, request: Request) -> Response:
        """Codice monouso (15 minuti) da mostrare come QR: l'app lo invia a POST /devices/register."""
        me = cast(AppUser, request.user)
        code = secrets.token_urlsafe(24)
        expires = timezone.now() + timedelta(minutes=CODE_TTL_MINUTES)
        DeviceEnrollmentCode.objects.create(code_hash=_hash(code), created_by=me, expires_at=expires)
        payload = json.dumps(
            {
                "v": 1,
                "api": settings.PUBLIC_API_URL,
                "issuer": settings.OIDC_ISSUER,
                "company": me.company.slug,
                "code": code,
            }
        )
        return Response(
            {"code": code, "expires_at": expires, "qr_payload": payload, "qr_svg": qr_svg_data_uri(payload)},
            status=status.HTTP_201_CREATED,
        )

    @action(detail=False, methods=["post"])
    def register(self, request: Request) -> Response:
        """Chiamata dall'app mobile con il token dell'utente e il codice letto dal QR."""
        me = cast(AppUser, request.user)
        d = cast(dict[str, Any], request.data)
        code = str(d.get("code", ""))
        install_id = str(d.get("install_id", "")).strip()
        if not code or not install_id:
            raise serializers.ValidationError({"code": ["Obbligatorio."], "install_id": ["Obbligatorio."]})
        enrollment = DeviceEnrollmentCode.objects.filter(code_hash=_hash(code), used_at__isnull=True).first()
        if enrollment is None or enrollment.expires_at < timezone.now():
            raise serializers.ValidationError({"code": ["Codice non valido o scaduto."]})
        platform = str(d.get("platform") or "")
        platform = platform if platform in ("ios", "android") else "android"
        needs_auth = me.company.devices_need_authorization
        device, created = MobileDevice.objects.update_or_create(
            install_id=install_id,
            defaults={
                "user": me,
                "name": str(d.get("name", "")).strip()[:120] or f"{me.full_name or me.email} - {platform}",
                "platform": platform,
                "os_version": str(d.get("os_version", ""))[:40],
                "app_version": str(d.get("app_version", ""))[:40],
                "status": MobileDevice.Status.PENDING if needs_auth else MobileDevice.Status.AUTHORIZED,
                "authorized_at": None if needs_auth else timezone.now(),
                "revoked_at": None,
                "last_seen_at": timezone.now(),
            },
        )
        enrollment.used_at = timezone.now()
        enrollment.used_by_device = device
        enrollment.save(update_fields=["used_at", "used_by_device", "updated_at"])
        audit.record(
            "device.register", "device", object_id=device.id, request=request, metadata={"created": created}
        )
        return Response(DeviceSerializer(device).data, status=status.HTTP_201_CREATED)

    @action(detail=False, methods=["post"])
    def heartbeat(self, request: Request) -> Response:
        me = cast(AppUser, request.user)
        data = cast(dict[str, Any], request.data)
        install_id = str(data.get("install_id", "")).strip()
        device = MobileDevice.objects.filter(install_id=install_id, user=me).first()
        if device is None:
            return Response({"code": "device_unknown", "detail": "Dispositivo non registrato."}, status=404)
        if device.status == MobileDevice.Status.REVOKED:
            return Response({"code": "device_revoked", "detail": "Dispositivo revocato."}, status=403)
        device.last_seen_at = timezone.now()
        fields = ["last_seen_at", "updated_at"]
        for f in ("app_version", "os_version"):
            if data.get(f):
                setattr(device, f, str(data[f])[:40])
                fields.append(f)
        device.save(update_fields=fields)
        return Response(status=204)


class DeviceStatusView(APIView):
    """Riepilogo per la pagina (conteggi per stato)."""

    permission_classes = [HasPermission]
    required_permissions = ("devices.view",)

    def get(self, request: Request) -> Response:
        counts = {s: 0 for s, _ in MobileDevice.Status.choices}
        for d in MobileDevice.objects.values_list("status", flat=True):
            counts[d] = counts.get(d, 0) + 1
        return Response(counts)
