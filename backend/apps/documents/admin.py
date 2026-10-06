"""
Django admin for `documents` -- `RecordFile` only, as an escape hatch (IR-476).

No office may remove a file another office filed, or a file with no party, and
an owner may remove none (`attachments.py`). When one has to go anyway, the
superuser removes it here. Django's admin log records who did, and so does the
IRIS audit trail, as it does for an API removal. There is no API override, for
RDCO or anyone (ADR-032 §10, IR-476 amendment).

Superuser only, and delete only: the API is how files are added and read.
Removing a row also removes the stored file, on the single delete and the bulk
action alike -- `QuerySet.delete()` would otherwise leave every file on disk.
"""

from django.contrib import admin

from apps.audit.services import create_audit_event

from .attachments import delete_record_file
from .models import RecordFile


def _remove(request, record_file):
    record = record_file.record
    delete_record_file(record_file)
    create_audit_event(
        "DELETE", request.user, record=record,
        metadata={"filename": record_file.filename, "via": "admin"},
    )


@admin.register(RecordFile)
class RecordFileAdmin(admin.ModelAdmin):
    list_display = ("filename", "record", "party", "uploaded_by", "created_at")
    list_filter = ("party",)
    list_select_related = ("record", "uploaded_by")
    search_fields = ("filename", "record__title")
    readonly_fields = ("record", "file", "filename", "party", "uploaded_by", "created_at")

    def has_module_permission(self, request):
        return request.user.is_superuser

    def has_view_permission(self, request, obj=None):
        return request.user.is_superuser

    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def delete_model(self, request, obj):
        _remove(request, obj)

    def delete_queryset(self, request, queryset):
        for record_file in queryset.select_related("record"):
            _remove(request, record_file)
