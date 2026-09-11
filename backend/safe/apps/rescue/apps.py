from django.apps import AppConfig


class RescueConfig(AppConfig):
    name = "safe.apps.rescue"
    label = "rescue"
    verbose_name = "SAFE eventi e persone"

    def ready(self) -> None:
        from . import signals, tasks  # noqa: F401  (tasks registra il job di anonimizzazione)
