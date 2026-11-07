from django.apps import AppConfig


class RecordsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.records"

    def ready(self):
        import apps.records.signals  # noqa: F401 — registers post_save handler
        import apps.records.retention  # noqa: F401 — registers download notes with the cleanup job (IR-794)

        # Refuse to start on an unreadable resubmission policy (IR-137,
        # ADR-004). Validating here rather than at first use is the whole
        # point: a misconfigured evaluation instance would otherwise boot
        # green and fail on a participant's first resubmission, mid-session,
        # with the run already underway. The return value is deliberately
        # discarded — this is a startup assertion, not a cache.
        from apps.records.lifecycle import resubmission_policy

        resubmission_policy()

        # IR-871: the review text sandbox's limits, as IR-830 checks intake's.
        # Partly set refuses to start; all unset only warns, and texts wait.
        from django.conf import settings
        from django.core.checks import Warning, register
        from django.core.exceptions import ImproperlyConfigured

        from apps.records.review_text.sandbox import LIMIT_NAMES, limits

        if any(getattr(settings, name, None) is not None for name in LIMIT_NAMES):
            try:
                limits()
            except ValueError as exc:
                raise ImproperlyConfigured(str(exc)) from exc

        @register()
        def check_review_text_limits(app_configs, **kwargs):
            try:
                limits()
            except ValueError:
                return [Warning(
                    "Review text reading is disabled: configure every REVIEW_TEXT_* limit.",
                    id="records.W001",
                )]
            return []
