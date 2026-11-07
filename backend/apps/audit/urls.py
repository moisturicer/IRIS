from django.urls import path
from .views import AuditEventExportView, AuditEventListView, AuditEventTypeListView

urlpatterns = [
    path("", AuditEventListView.as_view(), name="audit-list"),
    path("export/", AuditEventExportView.as_view(), name="audit-export"),
    path("event-types/", AuditEventTypeListView.as_view(), name="audit-event-types"),
    # Sessions endpoint lives under /accounts/sessions/ (accounts.views.ActiveSessionsView)
]
