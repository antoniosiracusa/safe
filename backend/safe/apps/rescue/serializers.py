from __future__ import annotations

import base64
import re
from typing import Any

from django.contrib.gis.geos import Point
from rest_framework import serializers

from safe.apps.lookups.fields import LookupCodeField
from safe.apps.lookups.models import Country, LookupValue
from safe.apps.org.models import Team
from safe.apps.territory.models import SkiArea, Slope, Zone

from .models import (
    Event,
    Person,
    PersonCondition,
    PersonDiagnosis,
    PersonEvacuationMean,
    PersonFirstAid,
    PersonInjury,
    PersonProtection,
)

# ----------------------------------------------------------------------------- helpers


class RefSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    name = serializers.CharField()


def ref(obj: Any) -> dict | None:
    return {"id": str(obj.id), "name": obj.name} if obj else None


def code(obj: LookupValue | None) -> str | None:
    return obj.code if obj else None


class TenantPKField(serializers.PrimaryKeyRelatedField):
    """FK verso un modello tenant: il queryset è calcolato a runtime (TenantManager)."""

    def __init__(self, model: Any, **kwargs: Any) -> None:
        self.model = model
        kwargs["queryset"] = model.all_objects.none()
        super().__init__(**kwargs)

    def get_queryset(self):  # noqa: ANN201
        return self.model.objects.all()


class GeometryField(serializers.Field):
    """GeoJSON Point WGS84 <-> PointField."""

    def to_representation(self, value: Point | None) -> dict | None:
        if value is None:
            return None
        return {"type": "Point", "coordinates": [value.x, value.y]}

    def to_internal_value(self, data: Any) -> Point | None:
        if data in (None, ""):
            return None
        if not isinstance(data, dict) or data.get("type") != "Point":
            raise serializers.ValidationError("Geometria non valida: atteso un GeoJSON Point.")
        try:
            lon, lat = (float(v) for v in data["coordinates"][:2])
        except (KeyError, TypeError, ValueError) as exc:
            raise serializers.ValidationError("Coordinate non valide.") from exc
        if not (-180 <= lon <= 180 and -90 <= lat <= 90):
            raise serializers.ValidationError("Coordinate fuori intervallo WGS84.")
        return Point(lon, lat, srid=4326)


class Base64Field(serializers.Field):
    def to_representation(self, value: bytes | memoryview | None) -> str | None:
        return base64.b64encode(bytes(value)).decode() if value is not None else None

    def to_internal_value(self, data: Any) -> bytes:
        try:
            return base64.b64decode(data, validate=True)
        except Exception as exc:  # noqa: BLE001
            raise serializers.ValidationError("Atteso base64.") from exc


# ----------------------------------------------------------------------------- persons

EXTENDED_PERSON_FIELDS = (
    "role",
    "equipment_condition",
    "rescue_refusal",
    "delivered_at",
    "protections",
    "conditions",
    "first_aid",
)


PERSON_RELATION_KEYS = (
    "evacuation_means",
    "secondary_diagnoses",
    "injuries",
    "protections",
    "conditions",
    "first_aid",
)


class EvacuationMeanSerializer(serializers.Serializer):
    mean = LookupCodeField("evacuation_mean", allow_null=False, required=True)
    order = serializers.IntegerField(min_value=1)


def validate_pii_blob(data: Any) -> dict | None:
    """Blob cifrato dal client (docs/01-architettura.md §7): {ciphertext, key_wrapped, key_version, fields}.
    Il server lo conserva opaco e non lo interpreta mai."""
    if data is None:
        return None
    if not isinstance(data, dict):
        raise serializers.ValidationError("Atteso un oggetto {ciphertext, key_wrapped, key_version, fields}.")
    try:
        ciphertext = base64.b64decode(data["ciphertext"], validate=True)
        key_wrapped = base64.b64decode(data["key_wrapped"], validate=True)
        key_version = int(data["key_version"])
        fields = list(data["fields"])
    except (KeyError, TypeError, ValueError) as exc:
        raise serializers.ValidationError("Blob cifrato non valido.") from exc
    if key_version < 1 or not fields or not all(isinstance(f, str) and len(f) <= 40 for f in fields):
        raise serializers.ValidationError("Blob cifrato non valido.")
    return {
        "ciphertext": ciphertext,
        "key_wrapped": key_wrapped,
        "key_version": key_version,
        "fields": fields,
    }


class PersonSerializer(serializers.ModelSerializer):
    """Lettura: sempre pseudonimizzata. Include i campi evento denormalizzati per la tabella Persone."""

    gender = serializers.SerializerMethodField()
    country_code = serializers.CharField(source="country_id", read_only=True)
    age_class = serializers.SerializerMethodField()
    has_identity = serializers.BooleanField(read_only=True)
    equipment = serializers.SerializerMethodField()
    equipment_owner = serializers.SerializerMethodField()
    insurance = serializers.SerializerMethodField()
    accommodation = serializers.SerializerMethodField()
    destination = serializers.SerializerMethodField()
    diagnosis = serializers.SerializerMethodField()
    secondary_diagnoses = serializers.SerializerMethodField()
    gravest_injury = serializers.SerializerMethodField()
    injury_place = serializers.SerializerMethodField()
    injuries = serializers.SerializerMethodField()
    evacuation_means = serializers.SerializerMethodField()
    responsibility = serializers.SerializerMethodField()
    extended = serializers.SerializerMethodField()
    event = serializers.SerializerMethodField()

    class Meta:
        model = Person
        fields = [
            "id",
            "event_id",
            "sequence",
            "age",
            "age_class",
            "gender",
            "country_code",
            "initials_firstname",
            "initials_surname",
            "has_identity",
            "pii_fields",
            "helmet",
            "equipment",
            "equipment_note",
            "equipment_owner",
            "insurance",
            "insurance_note",
            "accommodation",
            "accommodation_note",
            "destination",
            "destination_note",
            "diagnosis",
            "diagnosis_note",
            "secondary_diagnoses",
            "gravest_injury",
            "injury_place",
            "injuries",
            "evacuation_means",
            "evacuation_means_note",
            "responsibility",
            "administrative_violations",
            "note",
            "valid",
            "validation_errors",
            "anonymized_at",
            "extended",
            "event",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields

    @staticmethod
    def age_class_of(age: int | None) -> str:
        if age is None:
            return "unclassified"
        for limit, label in (
            (17, "0-17"),
            (24, "18-24"),
            (34, "25-34"),
            (44, "35-44"),
            (54, "45-54"),
            (64, "55-64"),
        ):
            if age <= limit:
                return label
        return "65+"

    def get_age_class(self, obj: Person) -> str:
        return obj.age_class_snapshot or self.age_class_of(obj.age)

    def get_gender(self, obj: Person) -> str | None:
        return code(obj.gender)

    def get_equipment(self, obj: Person) -> str | None:
        return code(obj.equipment)

    def get_equipment_owner(self, obj: Person) -> str | None:
        return code(obj.equipment_owner)

    def get_insurance(self, obj: Person) -> str | None:
        return code(obj.insurance)

    def get_accommodation(self, obj: Person) -> str | None:
        return code(obj.accommodation)

    def get_destination(self, obj: Person) -> str | None:
        return code(obj.destination)

    def get_diagnosis(self, obj: Person) -> str | None:
        return code(obj.diagnosis)

    def get_secondary_diagnoses(self, obj: Person) -> list[str]:
        return [d.diagnosis.code for d in obj.secondary_diagnoses.all()]

    def get_gravest_injury(self, obj: Person) -> str | None:
        return code(obj.gravest_injury)

    def get_injury_place(self, obj: Person) -> str | None:
        return code(obj.injury_place)

    def get_injuries(self, obj: Person) -> list[dict]:
        return [{"body_part": i.body_part.code, "rank": i.rank} for i in obj.injuries.all()]

    def get_evacuation_means(self, obj: Person) -> list[dict]:
        return [{"mean": m.mean.code, "order": m.order} for m in obj.evacuation_means.all()]

    def get_responsibility(self, obj: Person) -> str | None:
        return code(obj.responsibility)

    def get_extended(self, obj: Person) -> dict:
        return {
            "role": code(obj.role),
            "equipment_condition": code(obj.equipment_condition),
            "rescue_refusal": code(obj.rescue_refusal),
            "delivered_at": obj.delivered_at.isoformat() if obj.delivered_at else None,
            "protections": [p.protection.code for p in obj.person_protections.all()],
            "conditions": [c.condition.code for c in obj.person_conditions.all()],
            "first_aid": [f.first_aid.code for f in obj.person_first_aid.all()],
        }

    def get_event(self, obj: Person) -> dict:
        e = obj.event
        return {
            "id": str(e.id),
            "dateandtime": e.dateandtime.isoformat(),
            "season": e.season.code,
            "team_name": e.team.name,
            "zone_name": e.zone.name if e.zone else None,
            "slope_name": e.slope.name if e.slope else None,
            "locked": e.is_locked,
        }


class PersonWriteSerializer(serializers.ModelSerializer):
    client_uuid = serializers.UUIDField(required=False, allow_null=True)
    gender = LookupCodeField("gender")
    country_code = serializers.SlugRelatedField(
        source="country", slug_field="code", queryset=Country.objects.all(), required=False, allow_null=True
    )
    pii = serializers.DictField(required=False, allow_null=True, write_only=True)
    initials_firstname = serializers.CharField(max_length=3, required=False, allow_blank=True)
    initials_surname = serializers.CharField(max_length=3, required=False, allow_blank=True)
    equipment = LookupCodeField("equipment")
    equipment_owner = LookupCodeField("equipment_owner")
    insurance = LookupCodeField("insurance")
    accommodation = LookupCodeField("accommodation")
    destination = LookupCodeField("destination")
    diagnosis = LookupCodeField("diagnosis")
    secondary_diagnoses = serializers.ListField(
        child=LookupCodeField("diagnosis", allow_null=False), required=False
    )
    gravest_injury = LookupCodeField("body_part")
    injury_place = LookupCodeField("injury_place")
    injuries = serializers.ListField(child=serializers.DictField(), required=False)
    evacuation_means = EvacuationMeanSerializer(many=True, required=False)
    responsibility = LookupCodeField("responsibility")
    # estesi
    role = LookupCodeField("person_role")
    equipment_condition = LookupCodeField("equipment_condition")
    rescue_refusal = LookupCodeField("rescue_refusal")
    protections = serializers.ListField(child=LookupCodeField("protection", allow_null=False), required=False)
    conditions = serializers.ListField(child=LookupCodeField("condition", allow_null=False), required=False)
    first_aid = serializers.ListField(child=LookupCodeField("first_aid", allow_null=False), required=False)

    class Meta:
        model = Person
        fields = [
            "client_uuid",
            "sequence",
            "age",
            "gender",
            "country_code",
            "initials_firstname",
            "initials_surname",
            "pii",
            "helmet",
            "equipment",
            "equipment_note",
            "equipment_owner",
            "insurance",
            "insurance_note",
            "accommodation",
            "accommodation_note",
            "destination",
            "destination_note",
            "diagnosis",
            "diagnosis_note",
            "secondary_diagnoses",
            "gravest_injury",
            "injury_place",
            "injuries",
            "evacuation_means",
            "evacuation_means_note",
            "responsibility",
            "administrative_violations",
            "note",
            "role",
            "equipment_condition",
            "rescue_refusal",
            "delivered_at",
            "protections",
            "conditions",
            "first_aid",
        ]
        extra_kwargs = {"sequence": {"required": False}}

    @staticmethod
    def _initials(v: str) -> str:
        v = (v or "").strip().upper()
        if not re.fullmatch(r"[A-Z]{0,3}", v):
            raise serializers.ValidationError("Solo iniziali (max 3 lettere).")
        return v

    def validate_initials_firstname(self, v: str) -> str:
        return self._initials(v)

    def validate_initials_surname(self, v: str) -> str:
        return self._initials(v)

    def validate_pii(self, v: Any) -> dict | None:
        return validate_pii_blob(v)

    def validate_evacuation_means(self, means: list[dict]) -> list[dict]:
        orders = [m["order"] for m in means]
        if len(orders) != len(set(orders)):
            raise serializers.ValidationError("Ordine dei mezzi duplicato.")
        codes = [m["mean"].code for m in means]
        if len(codes) != len(set(codes)):
            raise serializers.ValidationError("Mezzo di evacuazione duplicato.")
        return means

    def validate_injuries(self, injuries: list[dict]) -> list[dict]:
        parts = {v.code: v for v in LookupValue.objects.active_for_tenant().dimension("body_part")}
        out = []
        for i in injuries:
            part = parts.get(i.get("body_part"))
            rank = i.get("rank", "secondary")
            if part is None or rank not in ("primary", "secondary"):
                raise serializers.ValidationError("Lesione non valida: atteso {body_part, rank}.")
            out.append({"body_part": part, "rank": rank})
        if sum(1 for i in out if i["rank"] == "primary") > 1:
            raise serializers.ValidationError("Una sola lesione principale.")
        return out

    def _apply_relations(self, person: Person, data: dict) -> None:
        if "evacuation_means" in data:
            person.evacuation_means.all().delete()
            PersonEvacuationMean.objects.bulk_create(
                [
                    PersonEvacuationMean(person=person, mean=m["mean"], order=m["order"])
                    for m in data["evacuation_means"]
                ]
            )
        if "secondary_diagnoses" in data:
            person.secondary_diagnoses.all().delete()
            PersonDiagnosis.objects.bulk_create(
                [PersonDiagnosis(person=person, diagnosis=d) for d in data["secondary_diagnoses"]]
            )
        if "injuries" in data:
            person.injuries.all().delete()
            PersonInjury.objects.bulk_create(
                [
                    PersonInjury(person=person, body_part=i["body_part"], rank=i["rank"])
                    for i in data["injuries"]
                ]
            )
            primary = next((i for i in data["injuries"] if i["rank"] == "primary"), None)
            if primary and not person.gravest_injury_id:
                person.gravest_injury = primary["body_part"]
                person.injury_place = primary["body_part"].parent
                person.save(update_fields=["gravest_injury", "injury_place", "updated_at"])
        if "protections" in data:
            person.person_protections.all().delete()
            PersonProtection.objects.bulk_create(
                [PersonProtection(person=person, protection=p) for p in data["protections"]]
            )
        if "conditions" in data:
            person.person_conditions.all().delete()
            PersonCondition.objects.bulk_create(
                [PersonCondition(person=person, condition=c) for c in data["conditions"]]
            )
        if "first_aid" in data:
            person.person_first_aid.all().delete()
            PersonFirstAid.objects.bulk_create(
                [PersonFirstAid(person=person, first_aid=f) for f in data["first_aid"]]
            )

    def _apply_pii(self, person: Person, pii: dict | None, present: bool) -> None:
        if not present:
            return
        if pii is None:
            person.pii_ciphertext = None
            person.pii_key_wrapped = None
            person.pii_key_version = None
            person.pii_fields = []
        else:
            person.pii_ciphertext = pii["ciphertext"]
            person.pii_key_wrapped = pii["key_wrapped"]
            person.pii_key_version = pii["key_version"]
            person.pii_fields = pii["fields"]

    def create(self, validated: dict) -> Person:
        event: Event = validated.pop("event")
        relations = {k: validated.pop(k) for k in PERSON_RELATION_KEYS if k in validated}
        pii_present = "pii" in validated
        pii = validated.pop("pii", None)
        if "sequence" not in validated:
            last = event.persons.order_by("-sequence").values_list("sequence", flat=True).first()
            validated["sequence"] = (last or 0) + 1
        person = Person(event=event, **validated)
        self._apply_pii(person, pii, pii_present)
        person.save()
        self._apply_relations(person, relations)
        return person

    def update(self, person: Person, validated: dict) -> Person:
        relations = {k: validated.pop(k) for k in PERSON_RELATION_KEYS if k in validated}
        pii_present = "pii" in validated
        pii = validated.pop("pii", None)
        for k, v in validated.items():
            setattr(person, k, v)
        self._apply_pii(person, pii, pii_present)
        person.save()
        self._apply_relations(person, relations)
        return person


# ----------------------------------------------------------------------------- events


class EventSerializer(serializers.ModelSerializer):
    """Rappresentazione in lista."""

    season = serializers.CharField(source="season.code", read_only=True)
    team = serializers.SerializerMethodField()
    ski_area = serializers.SerializerMethodField()
    zone = serializers.SerializerMethodField()
    slope = serializers.SerializerMethodField()
    difficulty = serializers.SerializerMethodField()
    location_type = serializers.SerializerMethodField()
    cause = serializers.SerializerMethodField()
    weather = serializers.SerializerMethodField()
    snow_condition = serializers.SerializerMethodField()
    wind = serializers.SerializerMethodField()
    visibility = serializers.SerializerMethodField()
    persons_count = serializers.IntegerField(read_only=True)
    has_geometry = serializers.SerializerMethodField()

    class Meta:
        model = Event
        fields = [
            "id",
            "season",
            "dateandtime",
            "team",
            "ski_area",
            "zone",
            "slope",
            "difficulty",
            "location_type",
            "location_description",
            "cause",
            "cause_note",
            "weather",
            "snow_condition",
            "wind",
            "visibility",
            "service_report",
            "witnesses",
            "persons_count",
            "valid",
            "fully_valid",
            "locked_at",
            "has_geometry",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields

    def get_team(self, obj: Event) -> dict | None:
        return ref(obj.team)

    def get_ski_area(self, obj: Event) -> dict | None:
        return ref(obj.ski_area)

    def get_zone(self, obj: Event) -> dict | None:
        return ref(obj.zone)

    def get_slope(self, obj: Event) -> dict | None:
        if not obj.slope:
            return None
        return {
            "id": str(obj.slope.id),
            "name": obj.slope.name,
            "regional_code": obj.slope.regional_code or None,
        }

    def get_difficulty(self, obj: Event) -> str | None:
        return code(obj.difficulty)

    def get_location_type(self, obj: Event) -> str | None:
        return code(obj.location_type)

    def get_cause(self, obj: Event) -> str | None:
        return code(obj.cause)

    def get_weather(self, obj: Event) -> str | None:
        return code(obj.weather)

    def get_snow_condition(self, obj: Event) -> str | None:
        return code(obj.snow_condition)

    def get_wind(self, obj: Event) -> str | None:
        return code(obj.wind)

    def get_visibility(self, obj: Event) -> str | None:
        return code(obj.visibility)

    def get_has_geometry(self, obj: Event) -> bool:
        return obj.geom is not None


class EventDetailSerializer(EventSerializer):
    geometry = GeometryField(source="geom", read_only=True)
    extended = serializers.SerializerMethodField()
    persons = serializers.SerializerMethodField()
    created_by = serializers.SerializerMethodField()

    class Meta(EventSerializer.Meta):
        fields = EventSerializer.Meta.fields + [
            "geometry",
            "altitude_m",
            "extended",
            "note",
            "validation_errors",
            "unlock_count",
            "last_unlocked_at",
            "persons",
            "created_by",
        ]
        read_only_fields = fields

    def get_extended(self, obj: Event) -> dict:
        return {
            "caller": obj.caller or None,
            "call_received_at": obj.call_received_at.isoformat() if obj.call_received_at else None,
            "time_since_incident": obj.time_since_incident.total_seconds()
            if obj.time_since_incident
            else None,
            "external_rescue_call_at": obj.external_rescue_call_at.isoformat()
            if obj.external_rescue_call_at
            else None,
            "location_feature": code(obj.location_feature),
            "traffic": code(obj.traffic),
            "snow_making": code(obj.snow_making),
            "event_type": code(obj.event_type),
            "operators": [
                {"user_id": str(o.user_id) if o.user_id else None, "name": o.name}
                for o in obj.operators.all()
            ],
        }

    def get_persons(self, obj: Event) -> list[dict]:
        persons = (
            obj.persons.filter(deleted_at__isnull=True)
            .select_related(
                "gender",
                "equipment",
                "equipment_owner",
                "insurance",
                "accommodation",
                "destination",
                "diagnosis",
                "gravest_injury",
                "injury_place",
                "responsibility",
                "role",
                "equipment_condition",
                "rescue_refusal",
                "event",
                "event__season",
                "event__team",
                "event__zone",
                "event__slope",
            )
            .prefetch_related(
                "evacuation_means__mean",
                "secondary_diagnoses__diagnosis",
                "injuries__body_part",
                "person_protections__protection",
                "person_conditions__condition",
                "person_first_aid__first_aid",
            )
        )
        return list(PersonSerializer(persons, many=True, context=self.context).data)

    def get_created_by(self, obj: Event) -> dict | None:
        u = obj.created_by
        return {"id": str(u.id), "name": u.full_name or u.email} if u else None


class ExtendedEventSerializer(serializers.Serializer):
    caller = serializers.CharField(max_length=120, required=False, allow_blank=True, allow_null=True)
    call_received_at = serializers.TimeField(required=False, allow_null=True)
    time_since_incident = serializers.DurationField(required=False, allow_null=True)
    external_rescue_call_at = serializers.TimeField(required=False, allow_null=True)
    location_feature = LookupCodeField("location_feature")
    traffic = LookupCodeField("traffic")
    snow_making = LookupCodeField("snow_making")
    event_type = LookupCodeField("event_type")
    operators = serializers.ListField(child=serializers.DictField(), required=False)


class EventWriteSerializer(serializers.ModelSerializer):
    client_uuid = serializers.UUIDField(required=False, allow_null=True)
    team = TenantPKField(Team)
    ski_area = TenantPKField(SkiArea, required=False, allow_null=True)
    zone = TenantPKField(Zone, required=False, allow_null=True)
    slope = TenantPKField(Slope, required=False, allow_null=True)
    difficulty = LookupCodeField("slope_difficulty")
    location_type = LookupCodeField("location_type")
    geometry = GeometryField(source="geom", required=False, allow_null=True)
    cause = LookupCodeField("cause")
    weather = LookupCodeField("weather")
    snow_condition = LookupCodeField("snow_condition")
    wind = LookupCodeField("wind")
    visibility = LookupCodeField("visibility")
    extended = ExtendedEventSerializer(required=False)

    class Meta:
        model = Event
        fields = [
            "client_uuid",
            "dateandtime",
            "team",
            "ski_area",
            "zone",
            "slope",
            "difficulty",
            "location_type",
            "location_description",
            "geometry",
            "altitude_m",
            "cause",
            "cause_note",
            "weather",
            "snow_condition",
            "wind",
            "visibility",
            "service_report",
            "witnesses",
            "note",
            "extended",
        ]

    def validate(self, attrs: dict) -> dict:
        zone = attrs.get("zone", getattr(self.instance, "zone", None))
        ski_area = attrs.get("ski_area", getattr(self.instance, "ski_area", None))
        slope = attrs.get("slope", getattr(self.instance, "slope", None))
        errors: dict[str, list[str]] = {}
        if zone and ski_area and zone.ski_area_id != ski_area.id:
            errors["zone"] = ["La zona non appartiene al comprensorio."]
        if slope and zone and slope.zone_id != zone.id:
            errors["slope"] = ["La pista non appartiene alla zona."]
        if errors:
            raise serializers.ValidationError(errors)
        return attrs

    SCALAR_EXTENDED = (
        "caller",
        "call_received_at",
        "time_since_incident",
        "external_rescue_call_at",
        "location_feature",
        "traffic",
        "snow_making",
        "event_type",
    )

    def _apply_extended_fields(self, event: Event, ext: dict | None) -> None:
        if not ext:
            return
        for k in self.SCALAR_EXTENDED:
            if k in ext:
                value = ext[k]
                setattr(event, k, value if value is not None else ("" if k == "caller" else None))

    def _apply_operators(self, event: Event, ext: dict | None) -> None:
        """Dopo il salvataggio: le righe figlie richiedono l'evento già presente (FK e RLS)."""
        if not ext or "operators" not in ext:
            return
        from .models import EventOperator

        event.operators.all().delete()
        EventOperator.objects.bulk_create(
            [
                EventOperator(
                    event=event, position=i + 1, user_id=o.get("user_id") or None, name=o.get("name") or ""
                )
                for i, o in enumerate(ext["operators"])
            ]
        )

    def create(self, validated: dict) -> Event:
        ext = validated.pop("extended", None)
        event = Event(**validated)
        event.created_by = self.context["request"].user
        self._apply_extended_fields(event, ext)
        event.save()
        self._apply_operators(event, ext)
        return event

    def update(self, event: Event, validated: dict) -> Event:
        ext = validated.pop("extended", None)
        for k, v in validated.items():
            setattr(event, k, v)
        self._apply_extended_fields(event, ext)
        event.save()
        self._apply_operators(event, ext)
        return event


class UnlockSerializer(serializers.Serializer):
    reason = serializers.CharField(max_length=500)
