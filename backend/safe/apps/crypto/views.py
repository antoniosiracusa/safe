"""Gestione chiavi per la cifratura end-to-end (docs/01-architettura.md §7, docs/07-dpia §5).

Il server conserva solo chiavi pubbliche, chiavi private cifrate (con passphrase o codice di recupero)
e data key sigillate: tutte le operazioni crittografiche avvengono nel browser. Le API qui sotto
spostano blob opachi e mantengono la coerenza (una chiave attiva per società, grant per utente,
kit di recupero corrente) registrando tutto in audit.
"""

from __future__ import annotations

import base64
from typing import Any, cast

from django.db import transaction
from django.db.models import QuerySet
from django.shortcuts import get_object_or_404
from django.utils import timezone
from drf_spectacular.utils import extend_schema
from rest_framework import serializers, status
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from safe.apps.audit import service as audit
from safe.apps.authz import resolve
from safe.apps.authz.drf import HasPermission
from safe.apps.core.exceptions import BusinessError
from safe.apps.org.models import AppUser
from safe.apps.rescue.models import Person

from .models import CompanyKey, CompanyKeyGrant, CompanyKeyRecovery, UserKey


def b64(data: bytes | memoryview | None) -> str | None:
    return base64.b64encode(bytes(data)).decode() if data is not None else None


class Base64Field(serializers.CharField):
    def __init__(self, *, min_len: int = 1, max_len: int = 16384, **kw: Any) -> None:
        super().__init__(**kw)
        self.min_len = min_len
        self.max_len = max_len

    def to_internal_value(self, data: Any) -> Any:  # bytes
        try:
            raw = base64.b64decode(str(data), validate=True)
        except Exception as exc:  # noqa: BLE001
            raise serializers.ValidationError("Base64 non valido.") from exc
        if not (self.min_len <= len(raw) <= self.max_len):
            raise serializers.ValidationError("Lunghezza non ammessa.")
        return raw


class RecoverySerializer(serializers.Serializer):
    encrypted_private_key = Base64Field(min_len=32)
    kdf_params = serializers.DictField()


class CompanyKeyInitSerializer(serializers.Serializer):
    public_key = Base64Field(min_len=32, max_len=64)
    wrapped_private_key = Base64Field(min_len=32)  # sealed box verso la chiave pubblica di chi inizializza
    recovery = RecoverySerializer()


class UserKeyPutSerializer(serializers.Serializer):
    algorithm = serializers.CharField(max_length=40, default="x25519-v1")
    public_key = Base64Field(min_len=32, max_len=64)
    private_key_encrypted = Base64Field(min_len=32)
    kdf_params = serializers.DictField()


class GrantSerializer(serializers.Serializer):
    user_id = serializers.UUIDField()
    wrapped_private_key = Base64Field(min_len=32)


class RewrapItemSerializer(serializers.Serializer):
    person_id = serializers.UUIDField()
    key_wrapped = Base64Field(min_len=32)


class RewrapSerializer(serializers.Serializer):
    items = RewrapItemSerializer(many=True)


def user(request: Request) -> AppUser:
    return cast(AppUser, request.user)


def active_key() -> CompanyKey | None:
    return CompanyKey.objects.filter(status=CompanyKey.Status.ACTIVE).first()


def key_payload(k: CompanyKey) -> dict[str, Any]:
    return {
        "id": str(k.id),
        "version": k.version,
        "algorithm": k.algorithm,
        "public_key": b64(k.public_key),
        "status": k.status,
        "created_at": k.created_at,
        "created_by": k.created_by.email if k.created_by else None,
        "retired_at": k.retired_at,
    }


def grant_payload(g: CompanyKeyGrant) -> dict[str, Any]:
    return {
        "id": str(g.id),
        "user": {
            "id": str(g.user_id),
            "email": g.user.email,
            "name": g.user.full_name,
            "status": g.user.status,
        },
        "company_key_id": str(g.company_key_id),
        "key_version": g.company_key.version,
        "granted_by": g.granted_by.email if g.granted_by else None,
        "created_at": g.created_at,
    }


def _create_recovery(key: CompanyKey, data: dict[str, Any], by: AppUser) -> CompanyKeyRecovery:
    CompanyKeyRecovery.objects.filter(company_key__company_id=key.company_id, used_at__isnull=True).update(
        used_at=timezone.now()
    )
    return CompanyKeyRecovery.objects.create(
        company_key=key,
        method=CompanyKeyRecovery.Method.RECOVERY_CODE,
        encrypted_private_key=data["encrypted_private_key"],
        kdf_params=data["kdf_params"],
        created_by=by,
    )


def _ensure_user_key(u: AppUser) -> UserKey:
    key = UserKey.objects.filter(user=u).first()
    if key is None:
        raise BusinessError("user_key_missing", "Prima crea la tua chiave personale.")
    return key


# --- chiave società ---------------------------------------------------------------------


class CompanyKeyView(APIView):
    permission_classes = [HasPermission]
    permission_map = {"get": ("persons.edit",), "post": ("crypto.manage_keys",)}

    @extend_schema(tags=["crypto"], responses={200: {"type": "object"}})
    def get(self, request: Request) -> Response:
        """Chiave pubblica attiva: serve a chiunque cifri dati identificativi."""
        key = active_key()
        if key is None:
            return Response(
                {"code": "company_key_missing", "detail": "Chiave società non inizializzata."}, status=404
            )
        return Response(key_payload(key))

    @extend_schema(tags=["crypto"], request=CompanyKeyInitSerializer, responses={201: {"type": "object"}})
    def post(self, request: Request) -> Response:
        """Inizializzazione: coppia generata nel browser del custode, grant per sé, kit di recupero."""
        if active_key() is not None:
            raise BusinessError("company_key_exists", "La chiave società esiste già: usa la rotazione.", 409)
        me = user(request)
        _ensure_user_key(me)
        ser = CompanyKeyInitSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        d = ser.validated_data
        with transaction.atomic():
            key = CompanyKey.objects.create(version=1, public_key=d["public_key"], created_by=me)
            CompanyKeyGrant.objects.create(
                company_key=key, user=me, wrapped_private_key=d["wrapped_private_key"], granted_by=me
            )
            _create_recovery(key, d["recovery"], me)
        resolve.invalidate(me.id)
        audit.record(
            "crypto.company_key_init",
            "company_key",
            object_id=key.id,
            request=request,
            metadata={"version": 1},
        )
        return Response(key_payload(key), status=status.HTTP_201_CREATED)


class CompanyKeyRotateView(APIView):
    permission_classes = [HasPermission]
    required_permissions = ("crypto.manage_keys",)

    @extend_schema(tags=["crypto"], request=CompanyKeyInitSerializer, responses={201: {"type": "object"}})
    def post(self, request: Request) -> Response:
        """Nuova versione attiva; la precedente resta 'retired' finché tutte le data key sono ri-sigillate."""
        me = user(request)
        _ensure_user_key(me)
        current = active_key()
        if current is None:
            raise BusinessError("company_key_missing", "Chiave società non inizializzata.")
        if not CompanyKeyGrant.objects.filter(company_key=current, user=me, revoked_at__isnull=True).exists():
            raise BusinessError(
                "no_key_grant", "Solo un custode con grant attiva può ruotare la chiave.", 409
            )
        ser = CompanyKeyInitSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        d = ser.validated_data
        with transaction.atomic():
            current.status = CompanyKey.Status.RETIRED
            current.retired_at = timezone.now()
            current.save(update_fields=["status", "retired_at", "updated_at"])
            key = CompanyKey.objects.create(
                version=current.version + 1, public_key=d["public_key"], created_by=me
            )
            CompanyKeyGrant.objects.create(
                company_key=key, user=me, wrapped_private_key=d["wrapped_private_key"], granted_by=me
            )
            _create_recovery(key, d["recovery"], me)
        for uid in CompanyKeyGrant.objects.filter(company_key=current).values_list("user_id", flat=True):
            resolve.invalidate(uid)
        audit.record(
            "crypto.company_key_rotate",
            "company_key",
            object_id=key.id,
            request=request,
            metadata={"from_version": current.version, "to_version": key.version},
        )
        remaining = Person.objects.filter(
            pii_ciphertext__isnull=False, pii_key_version__lt=key.version
        ).count()
        return Response({**key_payload(key), "persons_to_rewrap": remaining}, status=status.HTTP_201_CREATED)


class RewrapView(APIView):
    """Rotazione lato client: il custode scarica a lotti le data key sigillate con versioni precedenti,
    le apre con la chiave privata vecchia e le ri-sigilla con la pubblica nuova."""

    permission_classes = [HasPermission]
    required_permissions = ("crypto.manage_keys",)

    def _pending(self, key: CompanyKey) -> QuerySet:
        return Person.objects.filter(pii_ciphertext__isnull=False, pii_key_version__lt=key.version).order_by(
            "pii_key_version", "id"
        )

    @extend_schema(tags=["crypto"], responses={200: {"type": "object"}})
    def get(self, request: Request) -> Response:
        key = active_key()
        if key is None:
            raise BusinessError("company_key_missing", "Chiave società non inizializzata.")
        limit = min(int(request.query_params.get("limit", 200)), 500)
        pending = self._pending(key)
        items = [
            {"person_id": str(p.id), "key_wrapped": b64(p.pii_key_wrapped), "key_version": p.pii_key_version}
            for p in pending[:limit]
        ]
        return Response({"active_version": key.version, "remaining": pending.count(), "items": items})

    @extend_schema(tags=["crypto"], request=RewrapSerializer, responses={200: {"type": "object"}})
    def post(self, request: Request) -> Response:
        key = active_key()
        if key is None:
            raise BusinessError("company_key_missing", "Chiave società non inizializzata.")
        ser = RewrapSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        updated = 0
        with transaction.atomic():
            for item in ser.validated_data["items"]:
                updated += Person.objects.filter(
                    pk=item["person_id"], pii_ciphertext__isnull=False, pii_key_version__lt=key.version
                ).update(pii_key_wrapped=item["key_wrapped"], pii_key_version=key.version)
        remaining = self._pending(key).count()
        if updated:
            audit.record(
                "crypto.rewrap",
                "company_key",
                object_id=key.id,
                request=request,
                metadata={"updated": updated, "remaining": remaining},
            )
        return Response({"updated": updated, "remaining": remaining, "active_version": key.version})


# --- chiave personale ----------------------------------------------------------------------


class MyKeyView(APIView):
    permission_classes = [HasPermission]
    required_permissions: tuple[str, ...] = ()

    @extend_schema(tags=["crypto"], responses={200: {"type": "object"}})
    def get(self, request: Request) -> Response:
        me = user(request)
        key = UserKey.objects.filter(user=me).first()
        if key is None:
            return Response(
                {"code": "user_key_missing", "detail": "Chiave personale non creata."}, status=404
            )
        grants = CompanyKeyGrant.objects.filter(user=me, revoked_at__isnull=True).select_related(
            "company_key"
        )
        return Response(
            {
                "algorithm": key.algorithm,
                "public_key": b64(key.public_key),
                "private_key_encrypted": b64(key.private_key_encrypted),
                "kdf_params": key.kdf_params,
                "created_at": key.created_at,
                "rotated_at": key.rotated_at,
                "grants": [
                    {
                        "company_key_id": str(g.company_key_id),
                        "key_version": g.company_key.version,
                        "key_status": g.company_key.status,
                        "company_public_key": b64(g.company_key.public_key),
                        "wrapped_private_key": b64(g.wrapped_private_key),
                    }
                    for g in grants
                ],
            }
        )

    @extend_schema(tags=["crypto"], request=UserKeyPutSerializer, responses={200: {"type": "object"}})
    def put(self, request: Request) -> Response:
        """Crea o sostituisce la coppia personale. Sostituendola, le grant esistenti (sigillate per la
        vecchia pubblica) vengono revocate: un custode dovrà concederle di nuovo."""
        me = user(request)
        ser = UserKeyPutSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        d = ser.validated_data
        existing = UserKey.objects.filter(user=me).first()
        same_public = existing is not None and bytes(existing.public_key) == bytes(d["public_key"])
        with transaction.atomic():
            key, created = UserKey.objects.update_or_create(
                user=me,
                defaults={
                    "algorithm": d["algorithm"],
                    "public_key": d["public_key"],
                    "private_key_encrypted": d["private_key_encrypted"],
                    "kdf_params": d["kdf_params"],
                },
            )
            revoked = 0
            if not created and not same_public:
                # nuova coppia: le grant sigillate per la vecchia pubblica non sono più apribili
                key.rotated_at = timezone.now()
                key.save(update_fields=["rotated_at", "updated_at"])
                revoked = CompanyKeyGrant.objects.filter(user=me, revoked_at__isnull=True).update(
                    revoked_at=timezone.now(), revoked_by=me
                )
        resolve.invalidate(me.id)
        audit.record(
            "crypto.user_key_set",
            "user_key",
            object_id=key.id,
            request=request,
            metadata={"created": created, "grants_revoked": revoked, "passphrase_only": same_public},
        )
        return self.get(request)


# --- grant ----------------------------------------------------------------------------------


class GrantsView(APIView):
    permission_classes = [HasPermission]
    required_permissions = ("crypto.manage_keys",)

    @extend_schema(tags=["crypto"], responses={200: {"type": "object"}})
    def get(self, request: Request) -> Response:
        key = active_key()
        grants = (
            CompanyKeyGrant.objects.filter(company_key=key, revoked_at__isnull=True)
            .select_related("user", "company_key", "granted_by")
            .order_by("user__email")
            if key
            else []
        )
        candidates = [
            {"id": str(uk.user_id), "email": uk.user.email, "name": uk.user.full_name}
            for uk in UserKey.objects.select_related("user")
            .filter(user__status=AppUser.Status.ACTIVE)
            .exclude(user_id__in=[g.user_id for g in grants])
            .order_by("user__email")
        ]
        return Response(
            {
                "key": key_payload(key) if key else None,
                "grants": [grant_payload(g) for g in grants],
                "candidates": candidates,
            }
        )

    @extend_schema(tags=["crypto"], request=GrantSerializer, responses={201: {"type": "object"}})
    def post(self, request: Request) -> Response:
        key = active_key()
        if key is None:
            raise BusinessError("company_key_missing", "Chiave società non inizializzata.")
        ser = GrantSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        d = ser.validated_data
        target = get_object_or_404(AppUser.objects.all(), pk=d["user_id"])
        _ensure_user_key(target)
        if CompanyKeyGrant.objects.filter(company_key=key, user=target, revoked_at__isnull=True).exists():
            raise BusinessError("grant_exists", "L'utente ha già la grant.", 409)
        g = CompanyKeyGrant.objects.create(
            company_key=key,
            user=target,
            wrapped_private_key=d["wrapped_private_key"],
            granted_by=user(request),
        )
        resolve.invalidate(target.id)
        audit.record(
            "crypto.grant",
            "user",
            object_id=target.id,
            request=request,
            metadata={"key_version": key.version},
        )
        g = CompanyKeyGrant.objects.select_related("user", "company_key", "granted_by").get(pk=g.pk)
        return Response(grant_payload(g), status=status.HTTP_201_CREATED)


class GrantDetailView(APIView):
    permission_classes = [HasPermission]
    required_permissions = ("crypto.manage_keys",)

    @extend_schema(tags=["crypto"], responses={204: None})
    def delete(self, request: Request, user_id: str) -> Response:
        key = active_key()
        g = get_object_or_404(
            CompanyKeyGrant.objects.filter(company_key=key, revoked_at__isnull=True), user_id=user_id
        )
        if CompanyKeyGrant.objects.filter(company_key=key, revoked_at__isnull=True).count() <= 1:
            raise BusinessError(
                "last_custodian",
                "Non si può revocare l'ultimo custode: concedi prima la chiave a un altro utente.",
                409,
            )
        g.revoked_at = timezone.now()
        g.revoked_by = user(request)
        g.save(update_fields=["revoked_at", "revoked_by", "updated_at"])
        resolve.invalidate(g.user_id)
        audit.record("crypto.grant_revoke", "user", object_id=g.user_id, request=request)
        return Response(status=204)


class UserPublicKeyView(APIView):
    permission_classes = [HasPermission]
    required_permissions = ("crypto.manage_keys",)

    @extend_schema(tags=["crypto"], responses={200: {"type": "object"}})
    def get(self, request: Request, user_id: str) -> Response:
        target = get_object_or_404(AppUser.objects.all(), pk=user_id)
        key = UserKey.objects.filter(user=target).first()
        if key is None:
            return Response(
                {"code": "user_key_missing", "detail": "L'utente non ha ancora creato la sua chiave."},
                status=404,
            )
        return Response(
            {"user_id": str(target.id), "algorithm": key.algorithm, "public_key": b64(key.public_key)}
        )


# --- recupero -------------------------------------------------------------------------------


class RecoveryView(APIView):
    """Kit di recupero: la privata società cifrata con Argon2id(codice di 24 parole). La lettura è
    un evento sensibile (audit + throttling); la procedura completa è nel runbook M7."""

    permission_classes = [HasPermission]
    required_permissions = ("crypto.recovery",)
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "recovery"

    @extend_schema(tags=["crypto"], responses={200: {"type": "object"}})
    def get(self, request: Request) -> Response:
        key = active_key()
        rec = (
            CompanyKeyRecovery.objects.filter(company_key=key, used_at__isnull=True)
            .order_by("-created_at")
            .first()
            if key
            else None
        )
        audit.record(
            "crypto.recovery_read",
            "company_key",
            object_id=key.id if key else None,
            request=request,
            metadata={"found": rec is not None},
        )
        if key is None or rec is None:
            return Response(
                {"code": "recovery_missing", "detail": "Nessun kit di recupero disponibile."}, status=404
            )
        return Response(
            {
                "id": str(rec.id),
                "company_key_id": str(key.id),
                "key_version": key.version,
                "company_public_key": b64(key.public_key),
                "method": rec.method,
                "encrypted_private_key": b64(rec.encrypted_private_key),
                "kdf_params": rec.kdf_params,
                "created_at": rec.created_at,
            }
        )

    @extend_schema(tags=["crypto"], request=CompanyKeyInitSerializer, responses={201: {"type": "object"}})
    def post(self, request: Request) -> Response:
        """Dopo il recupero nel browser: grant per chi recupera e nuovo kit (il precedente è invalidato)."""
        me = user(request)
        _ensure_user_key(me)
        key = active_key()
        if key is None:
            raise BusinessError("company_key_missing", "Chiave società non inizializzata.")
        ser = CompanyKeyInitSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        d = ser.validated_data
        if bytes(d["public_key"]) != bytes(key.public_key):
            raise BusinessError(
                "public_key_mismatch", "La chiave recuperata non corrisponde alla chiave attiva."
            )
        with transaction.atomic():
            CompanyKeyGrant.objects.filter(company_key=key, user=me, revoked_at__isnull=True).update(
                revoked_at=timezone.now(), revoked_by=me
            )
            CompanyKeyGrant.objects.create(
                company_key=key, user=me, wrapped_private_key=d["wrapped_private_key"], granted_by=me
            )
            _create_recovery(key, d["recovery"], me)
        resolve.invalidate(me.id)
        audit.record("crypto.recovery_used", "company_key", object_id=key.id, request=request)
        return Response(key_payload(key), status=status.HTTP_201_CREATED)
