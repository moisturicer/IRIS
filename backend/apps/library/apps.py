from django.apps import AppConfig


class LibraryConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.library"

    def ready(self):
        # Deletes reading positions on replaced Manuscripts (IR-573).
        from . import signals  # noqa: F401
