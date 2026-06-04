from django.urls import path
from .views import ReviewViewSet, RecordAuthPinViewSet

review_list = ReviewViewSet.as_view({"get": "pending"})

urlpatterns = [
    path("pending/",       ReviewViewSet.as_view({"get": "pending"}),    name="reviews-pending"),
    path("submit/",        ReviewViewSet.as_view({"post": "submit"}),    name="reviews-submit"),
    path("resubmit/",      ReviewViewSet.as_view({"post": "resubmit"}),  name="reviews-resubmit"),
    path("approved/",      ReviewViewSet.as_view({"get": "approved"}),   name="reviews-approved"),
    path("declined/",      ReviewViewSet.as_view({"get": "declined"}),   name="reviews-declined"),
    path("analytics/",     ReviewViewSet.as_view({"get": "analytics"}),  name="reviews-analytics"),  # TODO M07 FR-M7-01
    path("pin/generate/",  RecordAuthPinViewSet.as_view({"post": "generate"}), name="pin-generate"),
    path("pin/verify/",    RecordAuthPinViewSet.as_view({"post": "verify"}),   name="pin-verify"),
]
