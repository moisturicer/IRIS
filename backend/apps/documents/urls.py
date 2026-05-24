from django.urls import path
from .views import (
    SubmitDocumentView,
    UploadSlotListView, RecordSlotListView,
    RecordUploadListView, RecordUploadCreateView,
    RecordUploadDownloadView, RecordFileListView, RecordFileUploadView,
    RecordFileDownloadAllView,
)

urlpatterns = [
    path("submit/", SubmitDocumentView.as_view(), name="document-submit"),
    path("slots/",                             UploadSlotListView.as_view(),          name="upload-slots"),
    # Combined slot+uploads view for DocumentsPage
    path("records/<int:pk>/slots/",            RecordSlotListView.as_view(),          name="record-slot-list"),
    path("uploads/",                           RecordUploadListView.as_view(),        name="record-uploads"),
    # POST /documents/uploads/ replaces old /documents/uploads/create/
    path("uploads/create/",                    RecordUploadCreateView.as_view(),      name="record-upload-create-legacy"),
    path("uploads/<int:pk>/download/",         RecordUploadDownloadView.as_view(),    name="record-upload-download"),
    path("files/",                             RecordFileListView.as_view(),          name="record-files"),
    path("files/upload/",                      RecordFileUploadView.as_view(),        name="record-file-upload"),
    path("files/download-all/",                RecordFileDownloadAllView.as_view(),   name="record-files-download-all"),
    # TODO: add UploadReview create endpoint for staff
    # TODO: add RecordFile delete endpoint
]
