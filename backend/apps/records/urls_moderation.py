from django.urls import path

from . import views_moderation

urlpatterns = [
    path("comments/", views_moderation.ReportedCommentsView.as_view(), name="comment-moderation"),
    path("comments/<int:comment_id>/remove/", views_moderation.RemoveCommentView.as_view(),
         name="comment-moderation-remove"),
    path("comments/<int:comment_id>/dismiss/", views_moderation.DismissReportsView.as_view(),
         name="comment-moderation-dismiss"),
]
