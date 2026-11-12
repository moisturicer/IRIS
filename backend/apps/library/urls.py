from django.urls import path

from .views import (
    HighlightDetailView,
    HighlightListView,
    ReadingNoteView,
    RecordHighlightsView,
    SavedFeedDetailView,
    SavedFeedListView,
    SavedRecordDetailView,
    SavedRecordListView,
)

urlpatterns = [
    path("saves/", SavedRecordListView.as_view(), name="library-saves"),
    path("saves/<int:record_id>/", SavedRecordDetailView.as_view(), name="library-save"),
    path("notes/<int:record_id>/", ReadingNoteView.as_view(), name="library-note"),
    path("highlights/", HighlightListView.as_view(), name="library-highlights"),
    path("highlights/<int:record_id>/", RecordHighlightsView.as_view(), name="library-record-highlights"),
    path("highlights/<int:record_id>/<int:highlight_id>/", HighlightDetailView.as_view(), name="library-highlight"),
    path("feeds/", SavedFeedListView.as_view(), name="library-feeds"),
    path("feeds/<int:feed_id>/", SavedFeedDetailView.as_view(), name="library-feed"),
]
