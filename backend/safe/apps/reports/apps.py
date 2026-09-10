from django.apps import AppConfig


class ReportsConfig(AppConfig):
    name = "safe.apps.reports"
    label = "reports"
    verbose_name = "SAFE rapporti PDF"

    def ready(self) -> None:
        from . import tasks  # noqa: F401  (registra l'handler del job)
