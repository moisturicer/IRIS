from django.urls import path
from .views import EmbedRecordView, EmbedAllView, EmbeddingJobListView

urlpatterns = [
    path("embed/<int:pk>/",    EmbedRecordView.as_view(),     name="ai-embed-record"),
    path("embed/all/",         EmbedAllView.as_view(),        name="ai-embed-all"),
    path("embed/jobs/",        EmbeddingJobListView.as_view(),name="ai-embed-jobs"),
]
