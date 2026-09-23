from django.urls import path

from .views import (
    AIStatusView,
    ChatQueryView,
    ChatStreamView,
    SemanticSearchView,
    ConversationListCreateView,
    ConversationDetailView,
    EmbedRecordView,
    EmbedAllView,
    EmbeddingJobListView,
    RecordOverviewView,
)

# Only routes backed by an implemented view are registered here. Summarisation
# stays out until its service exists — a 404 is more honest than a 500 from a
# `pass` body.
urlpatterns = [
    path("ask/",        ChatQueryView.as_view(),  name="ai-ask"),
    path("ask/stream/", ChatStreamView.as_view(), name="ai-ask-stream"),
    path("search/", SemanticSearchView.as_view(), name="ai-search"),
    path("status/", AIStatusView.as_view(),       name="ai-status"),
    path("records/<int:pk>/overview/", RecordOverviewView.as_view(),
         name="ai-record-overview"),
    path("conversations/",           ConversationListCreateView.as_view(),
         name="ai-conversations"),
    path("conversations/<int:pk>/",  ConversationDetailView.as_view(),
         name="ai-conversation-detail"),
    path("embed/<int:pk>/",    EmbedRecordView.as_view(),     name="ai-embed-record"),
    path("embed/all/",         EmbedAllView.as_view(),        name="ai-embed-all"),
    path("embed/jobs/",        EmbeddingJobListView.as_view(),name="ai-embed-jobs"),
]
