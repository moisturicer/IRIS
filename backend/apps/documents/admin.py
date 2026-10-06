"""
Django admin for `documents` -- `RecordFile` only, as an escape hatch (IR-476).

No office may remove a file another office filed, or a file with no party, and
an owner may remove none (`attachments.py`). When one has to go anyway, the
superuser removes it here, and Django's admin log records who did. There is no
API override, for RDCO or anyone.

Superuser only, and delete only: the API is how files are added and read.
Removing a row also removes the stored file, on the single delete and the bulk
action alike -- `QuerySet.delete()` would otherwise leave every file on disk.
"""

from django.contrib import admin

from .models import RecordFile


def _delete_stored_file(record_file):
    if record_file.file:
        record_file.file.delete(save=False)


@admin.register(RecordFile)
class RecordFileAdmin(admin.ModelAdmin):
    list_display = ("filename", "record", "party", "uploaded_by", "created_at")
    list_filter = ("party",)
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

    # The row goes first, so a failed delete never leaves a row with no file.
    def delete_model(self, request, obj):
        super().delete_model(request, obj)
        _delete_stored_file(obj)

    def delete_queryset(self, request, queryset):
        record_files = list(queryset)
        super().delete_queryset(request, queryset)
        for record_file in record_files:
            _delete_stored_file(record_file)
