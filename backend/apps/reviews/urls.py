from django.urls import path
from rest_framework.permissions import IsAuthenticated
from core.permissions import IsStaff
from .views import MyReviewsView, ReviewViewSet, RecordAuthPinViewSet

urlpatterns = [
    path("mine/",         MyReviewsView.as_view(),                     name="reviews-mine"),
    path("submit/",        ReviewViewSet.as_view({"post": "submit"}),    name="reviews-submit"),
    path("resubmit/",      ReviewViewSet.as_view({"post": "resubmit"}),  name="reviews-resubmit"),
    path("analytics/",     ReviewViewSet.as_view({"get": "analytics"}, permission_classes=[IsAuthenticated, IsStaff]),  name="reviews-analytics"),  # IR-626
    path("pin/generate/",  RecordAuthPinViewSet.as_view({"post": "generate"}), name="pin-generate"),
    path("pin/verify/",    RecordAuthPinViewSet.as_view({"post": "verify"}),   name="pin-verify"),
]
