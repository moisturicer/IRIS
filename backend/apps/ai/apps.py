from django.apps import AppConfig


class AiConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.ai"

    def ready(self):
        """Startup checks for the AI configuration (IR-379, IR-312, IR-838).

        Here rather than in a settings module because they must hold whichever
        settings module is loaded. It also puts them on every entry point --
        `runserver`, gunicorn, a Celery worker and `manage.py check` alike -- so
        a deploy fails rather than a reader's question.
        """
        from apps.ai.extraction import verify_extraction_configuration
        from apps.ai.inference import verify_inference_configuration
        from apps.ai.similarity import verify_novelty_configuration

        from apps.ai.admission.limits import verify_admission_configuration
        from apps.ai.grants.config import verify_grant_configuration
        from apps.ai.grants.reads import verify_research_read_configuration

        verify_extraction_configuration()
        verify_admission_configuration()
        verify_grant_configuration()
        verify_research_read_configuration()
        verify_inference_configuration()
        verify_novelty_configuration()

        from django.db.models.signals import pre_migrate

        from apps.ai.grants.migration_guard import refuse_runtime_login

        pre_migrate.connect(refuse_runtime_login, sender=self,
                            dispatch_uid="ai.refuse_runtime_login")
