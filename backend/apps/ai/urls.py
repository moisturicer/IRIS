from django.urls import path

from .views import AIStatusView, ChatQueryView, SemanticSearchView

# Only routes backed by an implemented view are registered here. Summarisation
# and embedding endpoints stay out until their services exist — a 404 is more
# honest than a 500 from a `pass` body.
urlpatterns = [
    path("ask/",    ChatQueryView.as_view(),      name="ai-ask"),
    path("search/", SemanticSearchView.as_view(), name="ai-search"),
    path("status/", AIStatusView.as_view(),       name="ai-status"),
]
