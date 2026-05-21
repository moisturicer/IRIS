import django_filters
from .models import Record


class RecordFilter(django_filters.FilterSet):
    year_from       = django_filters.NumberFilter(field_name="year_accomplished", lookup_expr="gte")
    year_to         = django_filters.NumberFilter(field_name="year_accomplished", lookup_expr="lte")
    classification  = django_filters.NumberFilter(field_name="classification_id")
    psced           = django_filters.NumberFilter(field_name="psced_id")
    record_type     = django_filters.NumberFilter(field_name="record_type_id")
    is_ip           = django_filters.BooleanFilter()
    pipeline_status = django_filters.CharFilter()

    class Meta:
        model  = Record
        fields = ["year_from", "year_to", "classification", "psced", "record_type", "is_ip", "pipeline_status"]
