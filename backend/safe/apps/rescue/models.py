"""Eventi (interventi) e persone coinvolte. Vedi docs/02-schema-dati.md."""

from __future__ import annotations

import datetime as dt
import zoneinfo
from typing import Any

from django.conf import settings
from django.contrib.gis.db import models as gis
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator, RegexValidator
from django.db import models
from django.db.models import Q

from safe.apps.core.ids import uuid7
from safe.apps.lookups.models import Country, LookupValue, lookup_fk
from safe.apps.org.models import Team
from safe.apps.tenancy.context import get_current_company_id
from safe.apps.tenancy.models import TenantModel
from safe.apps.territory.models import SkiArea, Slope, Zone


class Season(models.Model):
    """Stagione sciistica: 1 giugno → 31 maggio. Tabella globale."""

    id = models.UUIDField(primary_key=True, default=uuid7, editable=False)
    code = models.CharField(max_length=9, unique=True)  # '2025/2026'
    start_date = models.DateField()
    end_date = models.DateField()

    class Meta:
        db_table = "season"
        ordering = ["-start_date"]
        constraints = [
            models.CheckConstraint(condition=Q(end_date__gt=models.F("start_date")), name="chk_season_range")
        ]

    def __str__(self) -> str:
        return self.code

    @staticmethod
    def code_for(day: dt.date) -> str:
        start_year = day.year if day.month >= 6 else day.year - 1
        return f"{start_year}/{start_year + 1}"

    @classmethod
    def for_date(cls, day: dt.date) -> Season:
        code = cls.code_for(day)
        season, _ = cls.objects.get_or_create(
            code=code,
            defaults={
                "start_date": dt.date(int(code[:4]), 6, 1),
                "end_date": dt.date(int(code[:4]) + 1, 5, 31),
            },
        )
        return season

    @classmethod
    def current(cls, today: dt.date | None = None) -> Season:
        return cls.for_date(today or dt.date.today())


class ImportBatch(TenantModel):
    job = models.ForeignKey(
        "jobs.AsyncJob", null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    source_format = models.CharField(max_length=20)
    mapping = models.JSONField(default=dict)
    rows_total = models.IntegerField(default=0)
    rows_ok = models.IntegerField(default=0)
    rows_error = models.IntegerField(default=0)
    report = models.JSONField(default=list)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+"
    )

    class Meta(TenantModel.Meta):
        db_table = "import_batch"


class ActiveQuerySetMixin:
    def alive(self):  # noqa: ANN201
        return self.filter(deleted_at__isnull=True)  # type: ignore[attr-defined]


class Event(TenantModel):
    client_uuid = models.UUIDField(null=True, blank=True)  # idempotenza mobile
    legacy_id = models.CharField(max_length=40, blank=True, default="")
    import_batch = models.ForeignKey(
        ImportBatch, null=True, blank=True, on_delete=models.SET_NULL, related_name="events"
    )
    season = models.ForeignKey(Season, on_delete=models.PROTECT, related_name="events", editable=False)
    dateandtime = models.DateTimeField()
    team = models.ForeignKey(Team, on_delete=models.PROTECT, related_name="events")
    ski_area = models.ForeignKey(
        SkiArea, null=True, blank=True, on_delete=models.PROTECT, related_name="events"
    )
    zone = models.ForeignKey(Zone, null=True, blank=True, on_delete=models.PROTECT, related_name="events")
    slope = models.ForeignKey(Slope, null=True, blank=True, on_delete=models.PROTECT, related_name="events")
    difficulty = lookup_fk("slope_difficulty")
    location_type = lookup_fk("location_type")
    location_description = models.CharField(max_length=500, blank=True, default="")
    geom = gis.PointField(srid=4326, null=True, blank=True)
    altitude_m = models.DecimalField(max_digits=6, decimal_places=1, null=True, blank=True)
    cause = lookup_fk("cause")
    cause_note = models.TextField(blank=True, default="")
    weather = lookup_fk("weather")
    snow_condition = lookup_fk("snow_condition")
    wind = lookup_fk("wind")
    visibility = lookup_fk("visibility")
    service_report = models.BooleanField(default=False)
    witnesses = models.BooleanField(null=True, blank=True)  # NULL = non classificato
    # estesi (opzionali)
    caller = models.CharField(max_length=120, blank=True, default="")
    call_received_at = models.TimeField(null=True, blank=True)
    time_since_incident = models.DurationField(null=True, blank=True)
    external_rescue_call_at = models.TimeField(null=True, blank=True)
    location_feature = lookup_fk("location_feature")
    traffic = lookup_fk("traffic")
    snow_making = lookup_fk("snow_making")
    event_type = lookup_fk("event_type")
    note = models.TextField(blank=True, default="")
    # stato
    valid = models.BooleanField(default=False)
    fully_valid = models.BooleanField(default=False)
    validation_errors = models.JSONField(default=list, blank=True)
    locked_at = models.DateTimeField(null=True, blank=True)
    locked_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    unlock_count = models.PositiveIntegerField(default=0)
    last_unlocked_at = models.DateTimeField(null=True, blank=True)
    istat_comune_code = models.CharField(max_length=12, blank=True, default="")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    created_by_device = models.ForeignKey(
        "devices.MobileDevice", null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    deleted_at = models.DateTimeField(null=True, blank=True)

    class Meta(TenantModel.Meta):
        db_table = "event"
        ordering = ["-dateandtime"]
        constraints = [
            models.UniqueConstraint(
                fields=["company", "client_uuid"],
                condition=Q(client_uuid__isnull=False),
                name="ux_event_client_uuid",
            ),
            models.UniqueConstraint(
                fields=["company", "legacy_id"], condition=~Q(legacy_id=""), name="ux_event_legacy"
            ),
        ]
        indexes = [
            models.Index(
                fields=["company", "-dateandtime"],
                name="ix_event_company_date",
                condition=Q(deleted_at__isnull=True),
            ),
            models.Index(
                fields=["company", "season", "zone"],
                name="ix_event_season_zone",
                condition=Q(deleted_at__isnull=True),
            ),
            models.Index(
                fields=["company", "team", "dateandtime"],
                name="ix_event_team_date",
                condition=Q(deleted_at__isnull=True),
            ),
            models.Index(
                fields=["company", "slope"], name="ix_event_slope", condition=Q(deleted_at__isnull=True)
            ),
            models.Index(
                fields=["company", "ski_area"], name="ix_event_ski_area", condition=Q(deleted_at__isnull=True)
            ),
            models.Index(
                fields=["company", "locked_at"], name="ix_event_locked", condition=Q(deleted_at__isnull=True)
            ),
        ]

    def __str__(self) -> str:
        return f"Evento {self.id} del {self.dateandtime:%Y-%m-%d %H:%M}"

    @property
    def is_locked(self) -> bool:
        return self.locked_at is not None

    def local_date(self) -> dt.date:
        tz = zoneinfo.ZoneInfo(self.company.timezone if self.company_id else "Europe/Rome")  # type: ignore[attr-defined]
        return self.dateandtime.astimezone(tz).date()

    def clean(self) -> None:
        errors: dict[str, str] = {}
        if self.zone_id and self.ski_area_id and self.zone.ski_area_id != self.ski_area_id:  # type: ignore[attr-defined]
            errors["zone"] = "La zona non appartiene al comprensorio."
        if self.slope_id and self.zone_id and self.slope.zone_id != self.zone_id:  # type: ignore[attr-defined]
            errors["slope"] = "La pista non appartiene alla zona."
        if errors:
            raise ValidationError(errors)

    def save(self, *args: Any, **kwargs: Any) -> None:
        # coerenza territoriale e derivazioni (equivalente del trigger trg_event_before)
        if self.slope_id and not self.zone_id:
            self.zone_id = self.slope.zone_id  # type: ignore[attr-defined]
        if self.zone_id and not self.ski_area_id:
            self.ski_area_id = self.zone.ski_area_id  # type: ignore[attr-defined]
        if self.slope_id and not self.difficulty_id:
            self.difficulty_id = self.slope.difficulty_id  # type: ignore[attr-defined]
        if self.company_id is None:  # type: ignore[attr-defined]
            current = get_current_company_id()
            if current is None:
                raise RuntimeError("Nessun tenant nel contesto: impossibile salvare un evento.")
            self.company_id = current  # type: ignore[attr-defined]
        self.season = Season.for_date(self.local_date())
        super().save(*args, **kwargs)


class EventOperator(models.Model):
    event = models.ForeignKey(Event, on_delete=models.CASCADE, related_name="operators")
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    name = models.CharField(max_length=120, blank=True, default="")
    position = models.PositiveSmallIntegerField(default=1)

    class Meta:
        db_table = "event_operator"
        constraints = [models.UniqueConstraint(fields=["event", "position"], name="pk_event_operator")]
        ordering = ["position"]


INITIALS = RegexValidator(r"^[A-Z]{0,3}$", "Solo iniziali maiuscole (max 3).")


class Person(TenantModel):
    event = models.ForeignKey(Event, on_delete=models.CASCADE, related_name="persons")
    client_uuid = models.UUIDField(null=True, blank=True)
    sequence = models.PositiveSmallIntegerField(default=1)
    role = lookup_fk("person_role")
    # pseudonimizzati, in chiaro
    age = models.PositiveSmallIntegerField(
        null=True, blank=True, validators=[MinValueValidator(0), MaxValueValidator(120)]
    )
    gender = lookup_fk("gender")
    country = models.ForeignKey(
        Country, null=True, blank=True, on_delete=models.PROTECT, related_name="+", db_column="country_code"
    )
    initials_firstname = models.CharField(max_length=3, blank=True, default="", validators=[INITIALS])
    initials_surname = models.CharField(max_length=3, blank=True, default="", validators=[INITIALS])
    # identificativi, cifrati lato client
    pii_ciphertext = models.BinaryField(null=True, blank=True, editable=False)
    pii_key_wrapped = models.BinaryField(null=True, blank=True, editable=False)
    pii_key_version = models.PositiveIntegerField(null=True, blank=True)
    pii_fields = models.JSONField(default=list, blank=True)  # solo nomi dei campi, mai valori
    # attrezzatura
    helmet = models.BooleanField(null=True, blank=True)
    equipment = lookup_fk("equipment")
    equipment_note = models.TextField(blank=True, default="")
    equipment_owner = lookup_fk("equipment_owner")
    equipment_condition = lookup_fk("equipment_condition")
    protections = models.ManyToManyField(LookupValue, through="PersonProtection", related_name="+")
    # assicurazione, alloggio, destinazione
    insurance = lookup_fk("insurance")
    insurance_note = models.TextField(blank=True, default="")
    accommodation = lookup_fk("accommodation")
    accommodation_note = models.TextField(blank=True, default="")
    destination = lookup_fk("destination")
    destination_note = models.TextField(blank=True, default="")
    # clinica
    diagnosis = lookup_fk("diagnosis")
    diagnosis_note = models.TextField(blank=True, default="")
    gravest_injury = lookup_fk("body_part")
    injury_place = lookup_fk("injury_place")
    evacuation_means_note = models.TextField(blank=True, default="")
    rescue_refusal = lookup_fk("rescue_refusal")
    delivered_at = models.TimeField(null=True, blank=True)
    # responsabilità
    responsibility = lookup_fk("responsibility")
    administrative_violations = models.BooleanField(null=True, blank=True)
    note = models.TextField(blank=True, default="")
    # stato
    valid = models.BooleanField(default=False)
    validation_errors = models.JSONField(default=list, blank=True)
    anonymized_at = models.DateTimeField(null=True, blank=True)
    age_class_snapshot = models.CharField(max_length=12, blank=True, default="")
    deleted_at = models.DateTimeField(null=True, blank=True)

    class Meta(TenantModel.Meta):
        db_table = "person"
        ordering = ["event", "sequence"]
        constraints = [
            models.UniqueConstraint(
                fields=["company", "client_uuid"],
                condition=Q(client_uuid__isnull=False),
                name="ux_person_client_uuid",
            ),
            models.UniqueConstraint(fields=["event", "sequence"], name="ux_person_event_seq"),
            models.CheckConstraint(
                condition=(Q(pii_ciphertext__isnull=True) & Q(pii_key_wrapped__isnull=True))
                | (Q(pii_ciphertext__isnull=False) & Q(pii_key_wrapped__isnull=False)),
                name="chk_person_pii_pair",
            ),
        ]
        indexes = [
            models.Index(
                fields=["company", "event"],
                name="ix_person_company_event",
                condition=Q(deleted_at__isnull=True),
            ),
            models.Index(
                fields=["company", "country"], name="ix_person_country", condition=Q(deleted_at__isnull=True)
            ),
            models.Index(
                fields=["company", "diagnosis"],
                name="ix_person_diagnosis",
                condition=Q(deleted_at__isnull=True),
            ),
            models.Index(
                fields=["company", "equipment"],
                name="ix_person_equipment",
                condition=Q(deleted_at__isnull=True),
            ),
            models.Index(
                fields=["company", "anonymized_at"],
                name="ix_person_retention",
                condition=Q(pii_ciphertext__isnull=False),
            ),
        ]

    def __str__(self) -> str:
        return f"Persona {self.sequence} di {self.event_id}"

    @property
    def has_identity(self) -> bool:
        return self.pii_ciphertext is not None

    def save(self, *args: Any, **kwargs: Any) -> None:
        if self.company_id is None and self.event_id:  # type: ignore[attr-defined]
            self.company_id = self.event.company_id  # type: ignore[attr-defined]
        if self.gravest_injury_id and not self.injury_place_id:
            self.injury_place_id = self.gravest_injury.parent_id  # type: ignore[attr-defined]
        super().save(*args, **kwargs)


class PersonEvacuationMean(models.Model):
    person = models.ForeignKey(Person, on_delete=models.CASCADE, related_name="evacuation_means")
    mean = lookup_fk("evacuation_mean", null=False, blank=False)
    order = models.PositiveSmallIntegerField(validators=[MinValueValidator(1)])

    class Meta:
        db_table = "person_evacuation_mean"
        ordering = ["order"]
        constraints = [
            models.UniqueConstraint(fields=["person", "order"], name="pk_person_evacuation_order"),
            models.UniqueConstraint(fields=["person", "mean"], name="ux_person_evacuation_mean"),
        ]
        indexes = [models.Index(fields=["mean"], name="ix_pem_mean")]


class PersonDiagnosis(models.Model):
    person = models.ForeignKey(Person, on_delete=models.CASCADE, related_name="secondary_diagnoses")
    diagnosis = lookup_fk("diagnosis", null=False, blank=False)

    class Meta:
        db_table = "person_diagnosis"
        constraints = [models.UniqueConstraint(fields=["person", "diagnosis"], name="pk_person_diagnosis")]


class PersonInjury(models.Model):
    class Rank(models.TextChoices):
        PRIMARY = "primary", "Principale"
        SECONDARY = "secondary", "Secondaria"

    person = models.ForeignKey(Person, on_delete=models.CASCADE, related_name="injuries")
    body_part = lookup_fk("body_part", null=False, blank=False)
    rank = models.CharField(max_length=10, choices=Rank.choices)

    class Meta:
        db_table = "person_injury"
        constraints = [models.UniqueConstraint(fields=["person", "body_part"], name="pk_person_injury")]


class PersonProtection(models.Model):
    person = models.ForeignKey(Person, on_delete=models.CASCADE, related_name="person_protections")
    protection = lookup_fk("protection", null=False, blank=False)

    class Meta:
        db_table = "person_protection"
        constraints = [models.UniqueConstraint(fields=["person", "protection"], name="pk_person_protection")]
