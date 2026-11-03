from django.apps import AppConfig


class PublicationConfig(AppConfig):
    name = "apps.publication"
    default_auto_field = "django.db.models.BigAutoField"

    def ready(self):
        from . import signals  # noqa: F401
