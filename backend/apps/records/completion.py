"""A Record's one completion year (IR-1316): what the form records, else an import's."""

from django.db.models.functions import Coalesce

COMPLETION_YEAR = Coalesce("year_accomplished", "year_completed")


def with_completion_year(queryset):
    return queryset.annotate(completion_year=COMPLETION_YEAR)
