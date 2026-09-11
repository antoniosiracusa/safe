"""Crea una società con il suo primo amministratore (stato invitato: si attiva al primo login OIDC).

    python manage.py bootstrap_company --name "Val Fiorentina S.p.A." --slug valfiorentina \
        --admin-email admin@example.it --admin-first-name Mario --admin-last-name Rossi --invite

Il primo amministratore riceve anche il ruolo `key_custodian` (crypto.manage_keys/recovery): senza un
custode nessuno potrebbe inizializzare la chiave della società. Con `--invite` crea l'utente in Keycloak
e invia l'email di attivazione (password + MFA), come farebbe l'invito dall'interfaccia.
"""

from __future__ import annotations

from django.core.management.base import BaseCommand, CommandParser
from django.utils import timezone

from safe.apps.authz.models import Role, UserRole
from safe.apps.org.models import AppUser, Team, UserTeam
from safe.apps.tenancy.context import bypass_tenant, tenant_context
from safe.apps.tenancy.models import Company


class Command(BaseCommand):
    help = "Crea una società e il suo amministratore"

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("--name", required=True)
        parser.add_argument("--slug", required=True)
        parser.add_argument("--admin-email", required=True)
        parser.add_argument("--admin-first-name", default="")
        parser.add_argument("--admin-last-name", default="")
        parser.add_argument("--team", default="Squadra soccorso", help="Nome della prima squadra")
        parser.add_argument("--timezone", default="Europe/Rome")
        parser.add_argument("--tenant-type", default="company", choices=["company", "authority"])
        parser.add_argument("--no-custodian", action="store_true", help="Non assegna il ruolo custode chiavi")
        parser.add_argument("--invite", action="store_true", help="Crea l'utente in Keycloak e invia l'email")

    def handle(self, *args, **options) -> None:  # noqa: ANN002, ANN003
        with bypass_tenant():
            company, created = Company.objects.get_or_create(
                slug=options["slug"],
                defaults={
                    "name": options["name"],
                    "timezone": options["timezone"],
                    "tenant_type": options["tenant_type"],
                },
            )
        with tenant_context(company.id):
            team, _ = Team.objects.get_or_create(name=options["team"])
            user, user_created = AppUser.objects.get_or_create(
                email=options["admin_email"].lower(),
                defaults={
                    "first_name": options["admin_first_name"],
                    "last_name": options["admin_last_name"],
                    "status": AppUser.Status.INVITED,
                    "invited_at": timezone.now(),
                    "mfa_required": True,
                },
            )
            UserTeam.objects.get_or_create(user=user, team=team, defaults={"is_default": True})
            admin_role = Role.objects.get(code="company_admin", company=None)
            UserRole.objects.get_or_create(user=user, role=admin_role)
            if not options["no_custodian"]:
                custodian_role = Role.objects.get(code="key_custodian", company=None)
                UserRole.objects.get_or_create(user=user, role=custodian_role)
            roles = sorted(UserRole.objects.filter(user=user).values_list("role__code", flat=True))
            if options["invite"]:
                from safe.apps.org.views import send_invite

                send_invite(user)
        self.stdout.write(
            self.style.SUCCESS(
                f"Società {'creata' if created else 'esistente'}: {company.name} ({company.id}); "
                f"amministratore {'creato' if user_created else 'esistente'}: {user.email} "
                f"(ruoli: {', '.join(roles)})" + ("; invito inviato" if options["invite"] else "")
            )
        )
