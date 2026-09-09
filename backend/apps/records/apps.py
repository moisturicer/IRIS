from django.apps import AppConfig


class RecordsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.records"

    def ready(self):
        import apps.records.signals  # noqa: F401 — registers post_save handler

        # Refuse to start on an unreadable resubmission policy (IR-137,
        # ADR-004). Validating here rather than at first use is the whole
        # point: a misconfigured evaluation instance would otherwise boot
        # green and fail on a participant's first resubmission, mid-session,
        # with the run already underway. The return value is deliberately
        # discarded — this is a startup assertion, not a cache.
        from apps.records.lifecycle import resubmission_policy

        resubmission_policy()
