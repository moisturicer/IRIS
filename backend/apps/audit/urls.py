from django.urls import path
from .views import AuditEventListView, AuditEventExportView

urlpatterns = [
    path("", AuditEventListView.as_view(), name="audit-list"),
    path("export/", AuditEventExportView.as_view(), name="audit-export"),
    # Sessions endpoint lives under /accounts/sessions/ (accounts.views.ActiveSessionsView)
]
