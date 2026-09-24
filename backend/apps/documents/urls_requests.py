"""
The two document-request routes that are not under a Record (ADR-022 §5).

Creating and listing live on `RecordViewSet` (`/records/<id>/document-requests/`);
deciding an item and withdrawing a request are addressed by the request's own
id, as the ADR names them. Mounted at `/api/v1/`.
"""

from django.urls import path

from .views import DocumentRequestDecisionView, DocumentRequestItemDecisionView

urlpatterns = [
    path("document-requests/<int:pk>/", DocumentRequestDecisionView.as_view(),
         name="document-request-detail"),
    path("document-request-items/<int:pk>/", DocumentRequestItemDecisionView.as_view(),
         name="document-request-item-detail"),
]
