from django.apps import AppConfig


class LiveConfig(AppConfig):
    """Live updates (ADR-073, IR-1213): hints published on commit, streamed per tab."""
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.live"

    def ready(self):
        from . import signals  # noqa: F401  (connects the publish hooks)
