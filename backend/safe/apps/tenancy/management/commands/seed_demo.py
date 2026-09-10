"""Dati dimostrativi per lo sviluppo locale, coerenti con gli utenti del realm Keycloak di sviluppo
(`admin.demo@safe.local`, `rescuer.demo@safe.local`). Idempotente."""

from __future__ import annotations

from django.core.management import call_command
from django.core.management.base import BaseCommand

from safe.apps.authz.models import Role, UserRole
from safe.apps.lookups.models import LookupValue
from safe.apps.org.models import AppUser, Team, UserTeam
from safe.apps.tenancy.context import bypass_tenant, tenant_context
from safe.apps.tenancy.models import Company
from safe.apps.territory.models import SkiArea, Slope, Zone

SLOPES = [
    (
        "Val Fiorentina",
        [("LE CIAUNE", "C.1.24", "blue"), ("FERTAZZA", "C.1.3", "red"), ("SALERE", "C.1.17", "red")],
    ),
    (
        "Val di Zoldo",
        [
            ("Lendina", "C.1.24", "red"),
            ("Cristelin", "C.1.3", "red"),
            ("Della Grava", "C.1.17", "blue"),
            ("Campo Scuola Campetto", "C.1.19", "ski_school"),
            ("Le Coste (Cornia)", "C.1.20", "red"),
            ("Valgranda", "C.1.26", "black"),
            ("Foppe", "C.1.25", "red"),
        ],
    ),
]


class Command(BaseCommand):
    help = "Crea la società demo, utenti, squadre e territorio di esempio"

    def handle(self, *args, **options) -> None:  # noqa: ANN002, ANN003
        call_command(
            "bootstrap_company",
            name="Società Demo S.p.A.",
            slug="demo",
            admin_email="admin.demo@safe.local",
            admin_first_name="Admin",
            admin_last_name="Demo",
            team="Polizia Selva di Cadore",
        )
        with bypass_tenant():
            company = Company.objects.get(slug="demo")
        with tenant_context(company.id):
            body = {v.code: v for v in LookupValue.objects.filter(dimension="team_body")}
            police, _ = Team.objects.get_or_create(
                name="Polizia Selva di Cadore", defaults={"body": body["police"]}
            )
            carab, _ = Team.objects.get_or_create(
                name="Carabinieri Zoldo", defaults={"body": body["carabinieri"]}
            )
            alpini, _ = Team.objects.get_or_create(
                name="Truppe Alpine 7° Reggimento", defaults={"body": body["alpine_troops"]}
            )
            rescuer, _ = AppUser.objects.get_or_create(
                email="rescuer.demo@safe.local",
                defaults={
                    "first_name": "Soccorritore",
                    "last_name": "Demo",
                    "status": AppUser.Status.INVITED,
                },
            )
            UserTeam.objects.get_or_create(user=rescuer, team=carab, defaults={"is_default": True})
            UserRole.objects.get_or_create(user=rescuer, role=Role.objects.get(code="rescuer", company=None))

            area, _ = SkiArea.objects.get_or_create(name="Civetta")
            difficulty = {v.code: v for v in LookupValue.objects.filter(dimension="slope_difficulty")}
            for zone_name, slopes in SLOPES:
                zone, _ = Zone.objects.get_or_create(ski_area=area, name=zone_name)
                for name, code, diff in slopes:
                    Slope.objects.get_or_create(
                        zone=zone, name=name, defaults={"regional_code": code, "difficulty": difficulty[diff]}
                    )
            for team in (police, alpini):
                team.save()
        self.stdout.write(self.style.SUCCESS("Dati demo pronti (società 'demo')."))
