from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import RecordViewSet, DownloadRequestViewSet, DeleteRequestViewSet, DownloadRedeemView
from . import views_reference

router = DefaultRouter()
router.register(r"", RecordViewSet, basename="record")

urlpatterns = [
    path("", include(router.urls)),
    path("download/", DownloadRedeemView.as_view(), name="download-redeem"),
    path("download-requests/", include([
        path("", DownloadRequestViewSet.as_view({"get": "list", "post": "create"}), name="download-requests"),
        path("<int:pk>/", DownloadRequestViewSet.as_view({"patch": "partial_update"}), name="download-request-detail"),
    ])),
    path("delete-requests/", include([
        path("", DeleteRequestViewSet.as_view({"get": "list", "post": "create"}), name="delete-requests"),
        path("<int:pk>/", DeleteRequestViewSet.as_view({"patch": "partial_update"}), name="delete-request-detail"),
    ])),
    # Reference data
    path("classifications/", views_reference.ClassificationListView.as_view(), name="classifications"),
    path("psced-classifications/", views_reference.PSCEDListView.as_view(), name="psced"),
    path("record-types/", views_reference.RecordTypeListView.as_view(), name="record-types"),
]
