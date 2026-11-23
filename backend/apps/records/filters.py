import django_filters
from rest_framework.filters import OrderingFilter
from .completion import COMPLETION_YEAR, with_completion_year
from .models import Record
from .views_count import order_by_trending


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
    year_from       = django_filters.NumberFilter(method="filter_completed", lookup_expr="gte")
    year_to         = django_filters.NumberFilter(method="filter_completed", lookup_expr="lte")
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

    def filter_completed(self, queryset, name, value):
        bound = "gte" if name == "year_from" else "lte"
        return with_completion_year(queryset).filter(**{f"completion_year__{bound}": value})

    class Meta:
        model  = Record
        fields = [
            "id",
            "year_from", "year_to", "classification", "psced",
            "record_type", "is_ip", "ip_type", "pipeline_status", "department",
            "college", "for_commercialization",
        ]


class RecordOrderingFilter(OrderingFilter):
    """DRF's `?ordering=`, plus `?ordering=trending` (IR-369, CONTEXT.md **Trending**).

    The rule itself is `views_count.order_by_trending`, on the server rather
    than in the browser, so every caller gets the same tie-breaks. Most
    Viewed stays `-access_count`.
    """

    TRENDING = "trending"

    def filter_queryset(self, request, queryset, view):
        if request.query_params.get(self.ordering_param) == self.TRENDING:
            return order_by_trending(queryset)
        return super().filter_queryset(request, queryset, view)

    def get_ordering(self, request, queryset, view):
        """`year_accomplished` orders by the one completion year (IR-1316)."""
        ordering = super().get_ordering(request, queryset, view)
        return ordering and [
            COMPLETION_YEAR.desc(nulls_last=True) if term == "-year_accomplished"
            else COMPLETION_YEAR.asc(nulls_last=True) if term == "year_accomplished" else term
            for term in ordering
        ]
