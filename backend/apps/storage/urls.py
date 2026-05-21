from django.urls import path
from .views import (
    StorageListView,
    StorageFolderListView,
    StorageFolderDetailView,
    StorageFileListView,
    StorageFileDetailView,
    StorageFileDownloadView,
)

urlpatterns = [
    # Combined listing (returns folders + files + breadcrumb)
    path("",                          StorageListView.as_view(),        name="storage-list"),

    # Folders CRUD
    path("folders/",                  StorageFolderListView.as_view(),  name="storage-folder-list"),
    path("folders/<int:pk>/",         StorageFolderDetailView.as_view(),name="storage-folder-detail"),

    # Files CRUD + download
    path("files/",                    StorageFileListView.as_view(),    name="storage-file-list"),
    path("files/<int:pk>/",           StorageFileDetailView.as_view(),  name="storage-file-detail"),
    path("files/<int:pk>/download/",  StorageFileDownloadView.as_view(),name="storage-file-download"),
]
