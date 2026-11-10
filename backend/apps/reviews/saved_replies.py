"""
Saved replies (ADR-032 §7, 2026-11-04 Conveniences; IR-877): a person's own
reusable texts, inserted into a review comment.

    GET    /reviews/saved-replies/        the caller's replies, by title, with the limit
    POST   /reviews/saved-replies/        {"title", "body"}
    PATCH  /reviews/saved-replies/<id>/   {"title"?, "body"?}
    DELETE /reviews/saved-replies/<id>/

**Private.** Every query starts from `owner=request.user`, so another
person's reply answers the same 404 as a missing one. A reply belongs to no
record, so anyone signed in keeps their own (the design session decided this
widens the ADR's "a reviewer": it is private and decides nothing).
**Inserting only adds text**, and that is the comment box's own doing: the
server is never told a reply was used.
"""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.db.models.functions import Lower
from rest_framework import status
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .comments import MAX_BODY_LENGTH
from .models import MAX_SAVED_REPLIES, SavedReply

MAX_TITLE_LENGTH = 60

DUPLICATE_TITLE = "You already have a saved reply with that title."


def clean_title(raw) -> str:
    title = raw.strip() if isinstance(raw, str) else ""
    if not title:
        raise ValidationError({"title": ["Give the reply a title."]})
    if len(title) > MAX_TITLE_LENGTH:
        raise ValidationError({"title": [f"Use {MAX_TITLE_LENGTH} characters or fewer."]})
    return title


def clean_body(raw) -> str:
    body = raw.strip() if isinstance(raw, str) else ""
    if not body:
        raise ValidationError({"body": ["Write the reply's text."]})
    if len(body) > MAX_BODY_LENGTH:
        raise ValidationError({"body": [f"A saved reply is at most {MAX_BODY_LENGTH} characters."]})
    return body


def _taken(owner, title, *, excluding=None) -> bool:
    rows = SavedReply.objects.filter(owner=owner, title__iexact=title)
    if excluding is not None:
        rows = rows.exclude(pk=excluding)
    return rows.exists()


def _duplicate() -> ValidationError:
    return ValidationError({"title": [DUPLICATE_TITLE]})


def _entry(reply) -> dict:
    return {
        "id": reply.pk,
        "title": reply.title,
        "body": reply.body,
        "created_at": reply.created_at,
        "updated_at": reply.updated_at,
    }


def _body(request) -> dict:
    return request.data if isinstance(request.data, dict) else {}


def _locked(user):
    """Serialise one account's writes: the limit and the title check both
    count rows, so two simultaneous saves must not both pass them."""
    return get_user_model().objects.select_for_update().get(pk=user.pk)


def _save(reply):
    try:
        with transaction.atomic():
            reply.save()
    except IntegrityError:
        # The database's own case rule caught what the check missed.
        raise _duplicate()


class SavedReplyListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        rows = SavedReply.objects.filter(owner=request.user).order_by(Lower("title"), "pk")
        return Response({"results": [_entry(r) for r in rows], "limit": MAX_SAVED_REPLIES})

    def post(self, request):
        data = _body(request)
        title, body = clean_title(data.get("title")), clean_body(data.get("body"))
        with transaction.atomic():
            _locked(request.user)
            if SavedReply.objects.filter(owner=request.user).count() >= MAX_SAVED_REPLIES:
                return Response({
                    "code": "saved_reply_limit",
                    "detail": f"You have {MAX_SAVED_REPLIES} saved replies. Delete one to save another.",
                }, status=status.HTTP_400_BAD_REQUEST)
            if _taken(request.user, title):
                raise _duplicate()
            reply = SavedReply(owner=request.user, title=title, body=body)
            _save(reply)
        return Response(_entry(reply), status=status.HTTP_201_CREATED)


class SavedReplyDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def patch(self, request, reply_id):
        data = _body(request)
        if "title" not in data and "body" not in data:
            raise ValidationError({"detail": ["Give a title or a text to change."]})
        title = clean_title(data["title"]) if "title" in data else None
        body = clean_body(data["body"]) if "body" in data else None
        with transaction.atomic():
            _locked(request.user)
            reply = SavedReply.objects.filter(owner=request.user, pk=reply_id).first()
            if reply is None:
                raise NotFound()
            if title is not None:
                if _taken(request.user, title, excluding=reply.pk):
                    raise _duplicate()
                reply.title = title
            if body is not None:
                reply.body = body
            _save(reply)
        return Response(_entry(reply))

    def delete(self, request, reply_id):
        deleted, _ = SavedReply.objects.filter(owner=request.user, pk=reply_id).delete()
        if not deleted:
            raise NotFound()
        return Response(status=status.HTTP_204_NO_CONTENT)
