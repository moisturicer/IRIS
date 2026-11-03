from django.apps import AppConfig

class DocumentsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.documents"

    def ready(self):
        from django.core.checks import Warning, register
        from django.conf import settings
        from django.core.exceptions import ImproperlyConfigured
        from .validators import LIMIT_NAMES, validation_limits

        values = [getattr(settings, name, None) for name in LIMIT_NAMES]
        if any(value is not None for value in values):
            try:
                validation_limits()
            except ValueError as exc:
                raise ImproperlyConfigured(str(exc)) from exc

        @register()
        def check_pdf_limits(app_configs, **kwargs):
            try:
                validation_limits()
            except ValueError:
                return [Warning("PDF intake is disabled: configure every PDF_VALIDATION_* limit.",
                                id="documents.W001")]
            import sys
            if sys.platform != "linux":
                return [Warning("Bounded PDF intake is disabled: Linux RLIMIT_AS is required.",
                                id="documents.W002")]
            return []
