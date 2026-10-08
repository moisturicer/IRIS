from django.urls import path
from .views import MyReviewsView, ReviewViewSet, RecordAuthPinViewSet

urlpatterns = [
    path("mine/",         MyReviewsView.as_view(),                     name="reviews-mine"),
    path("submit/",        ReviewViewSet.as_view({"post": "submit"}),    name="reviews-submit"),
    path("resubmit/",      ReviewViewSet.as_view({"post": "resubmit"}),  name="reviews-resubmit"),
    path("analytics/",     ReviewViewSet.as_view({"get": "analytics"}),  name="reviews-analytics"),  # TODO M07 FR-M7-01
    path("pin/generate/",  RecordAuthPinViewSet.as_view({"post": "generate"}), name="pin-generate"),
    path("pin/verify/",    RecordAuthPinViewSet.as_view({"post": "verify"}),   name="pin-verify"),
]
