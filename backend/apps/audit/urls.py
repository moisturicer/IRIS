from django.urls import path
from .views import AuditEventListView, ActiveSessionsView

urlpatterns = [
    path("",          AuditEventListView.as_view(),  name="audit-list"),
    path("sessions/", ActiveSessionsView.as_view(),  name="audit-sessions"),
]
