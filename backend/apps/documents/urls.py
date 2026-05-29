from django.urls import path
from .views import (
    SubmitDocumentView,
    UploadSlotListView, RecordSlotListView,
    RecordUploadListView, RecordUploadCreateView,
    RecordUploadDownloadView, RecordUploadDeleteView,
    RecordFileListView, RecordFileUploadView,
    RecordFileDownloadView, RecordFileDeleteView, RecordFileDownloadAllView,
    UploadReviewCreateView,
)

urlpatterns = [
    path("submit/",                              SubmitDocumentView.as_view(),          name="document-submit"),
    path("slots/",                               UploadSlotListView.as_view(),          name="upload-slots"),
    # Combined slot+uploads view for DocumentsPage
    path("records/<int:pk>/slots/",              RecordSlotListView.as_view(),          name="record-slot-list"),
    path("uploads/",                             RecordUploadListView.as_view(),        name="record-uploads"),
    path("uploads/create/",                      RecordUploadCreateView.as_view(),      name="record-upload-create-legacy"),
    path("uploads/<int:pk>/download/",           RecordUploadDownloadView.as_view(),    name="record-upload-download"),
    path("uploads/<int:pk>/",                    RecordUploadDeleteView.as_view(),      name="record-upload-delete"),
    # Staff: set document status (For Application → Reviewed → Filed → Approved/Disapproved)
    path("upload-reviews/",                      UploadReviewCreateView.as_view(),      name="upload-reviews"),
    path("files/",                               RecordFileListView.as_view(),          name="record-files"),
    path("files/upload/",                        RecordFileUploadView.as_view(),        name="record-file-upload"),
    path("files/download-all/",                  RecordFileDownloadAllView.as_view(),   name="record-files-download-all"),
    path("files/<int:pk>/download/",             RecordFileDownloadView.as_view(),      name="record-file-download"),
    path("files/<int:pk>/",                      RecordFileDeleteView.as_view(),        name="record-file-delete"),
]
