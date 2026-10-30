from django.urls import path
from rest_framework.permissions import IsAuthenticated
from core.permissions import IsStaff
from .views import MyReviewsView, OfficeConsoleView, ReviewViewSet

urlpatterns = [
    path("mine/",         MyReviewsView.as_view(),                     name="reviews-mine"),
    path("office/",       OfficeConsoleView.as_view(),                 name="reviews-office"),
    path("submit/",        ReviewViewSet.as_view({"post": "submit"}),    name="reviews-submit"),
    path("resubmit/",      ReviewViewSet.as_view({"post": "resubmit"}),  name="reviews-resubmit"),
    path("analytics/",     ReviewViewSet.as_view({"get": "analytics"}, permission_classes=[IsAuthenticated, IsStaff]),  name="reviews-analytics"),  # IR-626
]
