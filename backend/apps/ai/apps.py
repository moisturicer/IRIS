from django.apps import AppConfig


class AiConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.ai"

    def ready(self):
        """Startup checks for the AI configuration (IR-317, IR-379, IR-464).

        Here rather than in a settings module because they must hold whichever
        settings module is loaded: the dangerous combination is `DEBUG=False`
        with the bypass set, and a check that lives only in `production.py`
        misses the deployment that reached `DEBUG=False` another way. It also
        puts both on every entry point -- `runserver`, gunicorn, a Celery
        worker and `manage.py check` alike -- so a deploy fails rather than a
        reader's question.
        """
        from apps.ai.evidence import (
            load_rule_set,
            verify_evidence_configuration,
        )
        from apps.ai.inference import verify_inference_configuration
        from apps.ai.policy.bypass import (
            install_bypass_if_enabled,
            verify_bypass_configuration,
        )

        verify_bypass_configuration()
        verify_inference_configuration()
        verify_evidence_configuration()
        install_bypass_if_enabled()
        # The evidence rule set is read here and nowhere else, so a
        # `.env` edit cannot remove a requirement between two questions.
        load_rule_set()
