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
from .setup_views import (
    SetupRecordTypeListView, SetupRecordTypeView, SetupRequirementCreateView,
    SetupRequirementOrderView, SetupRequirementView, SetupRequirementTemplateView,
    SetupManuscriptTemplateView, RequirementTemplateDownloadView,
    ManuscriptTemplateDownloadView,
)

urlpatterns = [
    path("submit/",                              SubmitDocumentView.as_view(),          name="document-submit"),
    path("slots/",                               UploadSlotListView.as_view(),          name="upload-slots"),
    # Templates, as downloads, for anyone signed in (ADR-063 decision 8, IR-971)
    path("slots/<int:pk>/template/",             RequirementTemplateDownloadView.as_view(), name="upload-slot-template"),
    path("record-types/<int:pk>/manuscript-template/", ManuscriptTemplateDownloadView.as_view(),
         name="record-type-manuscript-template"),
    # RDCO's Setup: Requirements & Templates (ADR-063 decisions 1-12, IR-971)
    path("setup/record-types/",                  SetupRecordTypeListView.as_view(),     name="setup-record-types"),
    path("setup/record-types/<int:pk>/",         SetupRecordTypeView.as_view(),         name="setup-record-type"),
    path("setup/record-types/<int:pk>/manuscript-template/", SetupManuscriptTemplateView.as_view(),
         name="setup-manuscript-template"),
    path("setup/record-types/<int:pk>/requirements/", SetupRequirementCreateView.as_view(),
         name="setup-requirements"),
    path("setup/record-types/<int:pk>/requirements/order/", SetupRequirementOrderView.as_view(),
         name="setup-requirement-order"),
    path("setup/requirements/<int:pk>/",         SetupRequirementView.as_view(),        name="setup-requirement"),
    path("setup/requirements/<int:pk>/template/", SetupRequirementTemplateView.as_view(),
         name="setup-requirement-template"),
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
