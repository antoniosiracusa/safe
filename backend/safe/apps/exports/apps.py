from django.apps import AppConfig


class ExportsConfig(AppConfig):
    name = "safe.apps.exports"
    label = "exports"
    verbose_name = "SAFE esportazioni"

    def ready(self) -> None:
        from . import tasks  # noqa: F401  (registra gli handler dei job)
