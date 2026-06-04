from django.urls import path
from .views import AuditEventListView

urlpatterns = [
    path("", AuditEventListView.as_view(), name="audit-list"),
    # Sessions endpoint lives under /accounts/sessions/ (accounts.views.ActiveSessionsView)
]
