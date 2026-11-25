"""Foto degli eventi (25/11/2026): al massimo 6 per evento, ridotte e cifrate sul dispositivo.

Il contenuto cifrato sta nell'archivio oggetti sotto `photos/<società>/<evento>/<foto>.bin`: un solo
prefisso per tutte le foto, così backup.sh lo copia in modo incrementale su Backblaze. Il server non può
decifrarle; le apre solo il browser di chi ha la chiave della società sbloccata.
"""

from __future__ import annotations

from typing import Any

from django.db import transaction
from django.utils import timezone

from safe.apps.audit import service as audit
from safe.apps.core.exceptions import ConflictError
from safe.apps.jobs import storage

from .models import Event, EventPhoto

MAX_PHOTOS_PER_EVENT = 6
# Le foto arrivano già ridotte (lato lungo 1600 px, circa 0,3-0,5 MB): 2 MB lascia margine e blocca
# per errore gli originali del telefono.
MAX_PHOTO_BYTES = 2 * 1024 * 1024
PHOTO_ALGORITHM = "xchacha20poly1305-x25519sealedbox-v1"


def object_key(photo: EventPhoto) -> str:
    return f"photos/{photo.company_id}/{photo.event_id}/{photo.id}.bin"


def touch_event(event: Event) -> None:
    """Le foto non sono campi dell'evento: si aggiorna `updated_at` perché il PDF in cache (chiave
    sull'ultima modifica dell'evento) e le statistiche vengano rigenerati."""
    event.updated_at = timezone.now()
    event.save(update_fields=["updated_at"])


def create(
    event: Event, *, data: bytes, key_wrapped: bytes, key_version: int, client_uuid: Any, request: Any
) -> tuple[EventPhoto, bool]:
    """Salva una foto cifrata. Ritorna (foto, creata): con lo stesso `client_uuid` restituisce quella già
    ricevuta (la coda della modalità pista può ripetere l'invio)."""
    if client_uuid:
        existing = EventPhoto.objects.filter(client_uuid=client_uuid).first()
        if existing is not None:
            return existing, False
    with transaction.atomic():
        Event.objects.select_for_update().filter(pk=event.pk).first()  # niente gare sul limite di 6
        if EventPhoto.objects.filter(event=event).count() >= MAX_PHOTOS_PER_EVENT:
            raise ConflictError(
                {
                    "detail": f"Al massimo {MAX_PHOTOS_PER_EVENT} foto per evento.",
                    "code": "photo_limit",
                }
            )
        photo = EventPhoto(
            event=event,
            company_id=event.company_id,
            client_uuid=client_uuid or None,
            size_bytes=len(data),
            key_wrapped=key_wrapped,
            key_version=key_version,
            created_by=request.user if request is not None else None,
        )
        photo.object_key = object_key(photo)
        storage.put(photo.object_key, data, "application/octet-stream")
        photo.save()
        touch_event(event)
    audit.record(
        "photo.create",
        "event_photo",
        object_id=photo.id,
        event_id=event.id,
        request=request,
        metadata={"size_bytes": photo.size_bytes},
    )
    return photo, True


def delete(photo: EventPhoto, *, request: Any = None, actor: Any = None, reason: str = "user") -> None:
    event_id = photo.event_id
    storage.delete(photo.object_key)
    photo.delete()
    audit.record(
        "photo.delete",
        "event_photo",
        object_id=photo.id,
        event_id=event_id,
        request=request,
        actor=actor,
        metadata={"reason": reason},
    )


def delete_for_event(event: Event, *, request: Any = None, actor: Any = None, reason: str) -> int:
    count = 0
    for photo in list(EventPhoto.objects.filter(event=event)):
        delete(photo, request=request, actor=actor, reason=reason)
        count += 1
    return count
