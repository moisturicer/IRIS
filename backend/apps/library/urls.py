from django.urls import path

from .views import SavedFeedDetailView, SavedFeedListView, SavedRecordDetailView, SavedRecordListView

urlpatterns = [
    path("saves/", SavedRecordListView.as_view(), name="library-saves"),
    path("saves/<int:record_id>/", SavedRecordDetailView.as_view(), name="library-save"),
    path("feeds/", SavedFeedListView.as_view(), name="library-feeds"),
    path("feeds/<int:feed_id>/", SavedFeedDetailView.as_view(), name="library-feed"),
]
