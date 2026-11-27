"""
The two document-request routes that are not under a Record (ADR-022 §5).

Creating and listing live on `RecordViewSet` (`/records/<id>/document-requests/`);
withdrawing a request is addressed by the request's own id, as the ADR names
it. Mounted at `/api/v1/`. Deciding an item is gone: a sent document is
supplied (ADR-022 Amendment 10, IR-1338).
"""

from django.urls import path

from .views import DocumentRequestDecisionView

urlpatterns = [
    path("document-requests/<int:pk>/", DocumentRequestDecisionView.as_view(),
         name="document-request-detail"),
]
