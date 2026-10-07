"""
The reviewer-seat routes (ADR-032 §4, IR-415), addressed by the assignment or
seat's own id as the document-request routes are. Mounted at `/api/v1/`.
"""

from django.urls import path

from .seat_views import (
    AddReviewerView,
    AssignView,
    ClaimView,
    OpenReviewView,
    ReassignView,
    WithdrawView,
)

urlpatterns = [
    path("assignments/<int:pk>/claim/", ClaimView.as_view(), name="assignment-claim"),
    path("assignments/<int:pk>/assign/", AssignView.as_view(), name="assignment-assign"),
    path("assignments/<int:pk>/add-reviewer/", AddReviewerView.as_view(),
         name="assignment-add-reviewer"),
    path("seats/<int:pk>/open/", OpenReviewView.as_view(), name="seat-open"),
    path("seats/<int:pk>/reassign/", ReassignView.as_view(), name="seat-reassign"),
    path("seats/<int:pk>/withdraw/", WithdrawView.as_view(), name="seat-withdraw"),
]
