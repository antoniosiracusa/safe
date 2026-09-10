"""Invalidazione cache statistiche: ogni scrittura su evento/persona incrementa company.data_version."""

from __future__ import annotations

from django.db.models import F
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from safe.apps.tenancy.models import Company

from .models import Event, Person


def _bump(company_id) -> None:  # noqa: ANN001
    Company.objects.filter(id=company_id).update(data_version=F("data_version") + 1)


@receiver(post_save, sender=Event)
@receiver(post_delete, sender=Event)
@receiver(post_save, sender=Person)
@receiver(post_delete, sender=Person)
def bump_data_version(sender, instance, **kwargs) -> None:  # noqa: ANN001
    if instance.company_id:
        _bump(instance.company_id)
