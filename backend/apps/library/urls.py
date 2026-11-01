from django.urls import path

from .views import SavedRecordDetailView, SavedRecordListView

urlpatterns = [
    path("saves/", SavedRecordListView.as_view(), name="library-saves"),
    path("saves/<int:record_id>/", SavedRecordDetailView.as_view(), name="library-save"),
]
