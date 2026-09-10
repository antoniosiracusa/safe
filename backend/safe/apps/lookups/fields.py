"""Campo DRF per i vocabolari controllati: in API viaggia il `code` (stringa), in DB la FK.
Il queryset è costruito a ogni richiesta, così rispetta tenant e valori disattivati."""

from __future__ import annotations

from typing import Any

from rest_framework import serializers

from .models import LookupValue


class LookupCodeField(serializers.SlugRelatedField):
    def __init__(self, dimension: str, **kwargs: Any) -> None:
        self.dimension = dimension
        kwargs.setdefault("slug_field", "code")
        kwargs.setdefault("allow_null", True)
        kwargs.setdefault("required", False)
        kwargs["queryset"] = LookupValue.all_objects.none()  # sostituito da get_queryset()
        super().__init__(**kwargs)

    def get_queryset(self):  # noqa: ANN201
        return LookupValue.objects.active_for_tenant().dimension(self.dimension)

    def to_internal_value(self, data: Any) -> Any:
        if data in ("", None):
            return None
        try:
            return super().to_internal_value(data)
        except serializers.ValidationError as exc:
            raise serializers.ValidationError(
                f"Valore '{data}' non ammesso per la dimensione '{self.dimension}'."
            ) from exc
