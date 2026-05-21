from django.urls import path
from .views import SemanticSearchView, AskView, EmbedRecordView, EmbedAllView, EmbeddingJobListView

urlpatterns = [
    path("search/",         SemanticSearchView.as_view(), name="ai-search"),
    path("ask/",            AskView.as_view(),            name="ai-ask"),
    path("embed/<int:pk>/", EmbedRecordView.as_view(),    name="ai-embed-record"),
    path("embed/all/",      EmbedAllView.as_view(),       name="ai-embed-all"),
    path("embed/jobs/",     EmbeddingJobListView.as_view(),name="ai-embed-jobs"),
]
