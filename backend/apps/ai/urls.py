from django.urls import path
from .views.brief import PaperBriefView
from .views.grants import (
    ReaderPathView, ReaderSessionGrantView, RunGrantRenewView, RunGrantView, RuntimeEdgeGrantView,
)

from .views import (
    AIStatusView,
    RetiredAnswerView,
    RunStreamView,
    RunCancelView,
    ConversationListView,
    ConversationDetailView,
    EmbedRecordView,
    EmbedAllView,
    EmbeddingJobListView,
    RecordOverviewView,
)

# Django stopped answering questions in IR-957: the AI runtime answers every
# one, through the same-origin edge `runtime/edge-grant/` authenticates. The
# old answer routes stay registered so a page loaded before the switch gets
# 410 Gone, not a 404 that reads like a missing conversation.
urlpatterns = [
    path("records/<int:pk>/brief/", PaperBriefView.as_view(), name="ai-paper-brief"),
    path("ask/",        RetiredAnswerView.as_view(), name="ai-ask"),
    path("ask/stream/", RetiredAnswerView.as_view(), name="ai-ask-stream"),
    path("ask/runs/<uuid:pk>/stream/", RunStreamView.as_view(), name="ai-ask-run-stream"),
    path("ask/runs/<uuid:pk>/cancel/", RunCancelView.as_view(), name="ai-ask-run-cancel"),
    path("ask/runs/<uuid:pk>/retry/", RetiredAnswerView.as_view(), name="ai-ask-run-retry"),
    path("ask/runs/<uuid:pk>/grant/", RunGrantView.as_view(), name="ai-ask-run-grant"),
    path("ask/runs/<uuid:pk>/grant/renew/", RunGrantRenewView.as_view(), name="ai-ask-run-grant-renew"),
    path("runtime/grant/", ReaderSessionGrantView.as_view(), name="ai-runtime-grant"),
    path("runtime/edge-grant/", RuntimeEdgeGrantView.as_view(), name="ai-runtime-edge-grant"),
    path("reader/", ReaderPathView.as_view(), name="ai-reader-path"),
    path("search/", RetiredAnswerView.as_view(), name="ai-search"),
    path("status/", AIStatusView.as_view(),       name="ai-status"),
    path("records/<int:pk>/overview/", RecordOverviewView.as_view(),
         name="ai-record-overview"),
    path("conversations/",           ConversationListView.as_view(),
         name="ai-conversations"),
    path("conversations/<int:pk>/",  ConversationDetailView.as_view(),
         name="ai-conversation-detail"),
    path("embed/<int:pk>/",    EmbedRecordView.as_view(),     name="ai-embed-record"),
    path("embed/all/",         EmbedAllView.as_view(),        name="ai-embed-all"),
    path("embed/jobs/",        EmbeddingJobListView.as_view(),name="ai-embed-jobs"),
]
