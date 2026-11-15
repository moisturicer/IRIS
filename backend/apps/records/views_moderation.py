"""
The Reported comments queue and comment removal, for RDCO and the System Admin
(ADR-032 §7, amendment 2026-10-31; IR-691). The rules are
`apps.records.comment_moderation`'s.
"""

from django.http import Http404
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from core.permissions import IsCommentModerator

from . import comment_moderation as moderation


def _answer(act):
    try:
        act()
    except moderation.CommentNotFound:
        raise Http404("No comment matches the given query.")
    except moderation.CommentError as exc:
        return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
    except moderation.AlreadyHandled as exc:
        return Response({"detail": str(exc)}, status=status.HTTP_409_CONFLICT)
    return Response(status=status.HTTP_204_NO_CONTENT)


class ReportedCommentsView(APIView):
    """GET /moderation/comments/ -- every comment with an open report, newest report first."""

    permission_classes = [IsAuthenticated, IsCommentModerator]

    def get(self, request):
        return Response(moderation.queue(request.user))


class RemoveCommentView(APIView):
    """POST /moderation/comments/<comment_id>/remove/ `{"reason": str}` -- remove any comment (204)."""

    permission_classes = [IsAuthenticated, IsCommentModerator]

    def post(self, request, comment_id):
        return _answer(lambda: moderation.remove(request.user, comment_id, reason=request.data.get("reason")))


class DismissReportsView(APIView):
    """POST /moderation/comments/<comment_id>/dismiss/ -- close a comment's open reports (204)."""

    permission_classes = [IsAuthenticated, IsCommentModerator]

    def post(self, request, comment_id):
        return _answer(lambda: moderation.dismiss(request.user, comment_id))
