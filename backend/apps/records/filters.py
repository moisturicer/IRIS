import django_filters
from .models import Record


class NumberInFilter(django_filters.BaseInFilter, django_filters.NumberFilter):
    """Comma-separated numeric list, e.g. ?college=1,5 — for multi-select filters."""


class RecordFilter(django_filters.FilterSet):
    # ?id=3,7,12 — resolve a set of ids in one call.
    #
    # This exists so client-held id lists (My Library's saved records, which
    # live in localStorage) resolve through the *list* queryset, which applies
    # publicly_visible(). Resolving them one-by-one through the detail route
    # would bypass that: get_queryset() only filters on `list`, so `retrieve`
    # still returns any record to any authenticated user. Ids that fail the
    # predicate simply drop out of the response.
    id              = NumberInFilter(field_name="id", lookup_expr="in")
    year_from       = django_filters.NumberFilter(field_name="year_accomplished", lookup_expr="gte")
    year_to         = django_filters.NumberFilter(field_name="year_accomplished", lookup_expr="lte")
    classification  = NumberInFilter(field_name="classification_id", lookup_expr="in")
    psced           = django_filters.NumberFilter(field_name="psced_id")
    record_type     = django_filters.NumberFilter(field_name="record_type_id")
    is_ip           = django_filters.BooleanFilter()
    ip_type         = django_filters.CharFilter()          # FR-M5-05: filter by IP type
    pipeline_status = django_filters.CharFilter()
    department      = django_filters.NumberFilter(
        field_name="owners__user__student_profile__course__department_id", distinct=True
    )
    # Joins span a reverse FK (owners), so a record with several owners in the same
    # college would otherwise appear once per owner — hence distinct.
    college         = NumberInFilter(
        field_name="owners__user__student_profile__course__department__college_id",
        lookup_expr="in",
        distinct=True,
    )
    for_commercialization = django_filters.BooleanFilter()   # KTTO commercial-ready feed

    class Meta:
        model  = Record
        fields = [
            "id",
            "year_from", "year_to", "classification", "psced",
            "record_type", "is_ip", "ip_type", "pipeline_status", "department",
            "college", "for_commercialization",
        ]
