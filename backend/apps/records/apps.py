from django.apps import AppConfig


class RecordsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.records"

    def ready(self):
        import apps.records.signals  # noqa: F401 — registers post_save handler
