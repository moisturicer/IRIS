from django.apps import AppConfig


class AiConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.ai"

    def ready(self):
        """Startup checks for the development disclosure bypass (IR-317).

        Here rather than in a settings module because it must hold whichever
        settings module is loaded: the dangerous combination is `DEBUG=False`
        with the bypass set, and a check that lives only in `production.py`
        misses the deployment that reached `DEBUG=False` another way.
        """
        from apps.ai.policy.bypass import (
            install_bypass_if_enabled,
            verify_bypass_configuration,
        )

        verify_bypass_configuration()
        install_bypass_if_enabled()
