"""
The reader's saved Records (IR-566, ADR-044 §3-§5).

Two rules hold for every request:

* **The owner is the authenticated user.** No body or URL names an owner, and
  every query starts from `SavedRecord.objects.filter(owner=request.user)`, so
  another reader's saves cannot be addressed at all.
* **The Record is rechecked against `Record.objects.visible_to(user)`** -- the
  one visibility predicate. Saving a Record you cannot read is a 404 identical
  to a missing one. A saved Record you can no longer read is listed as
  `{"record_id": <id>, "available": false}` and nothing else: the id is the
  one the reader supplied, so it discloses nothing new.

Every write is idempotent, so the interface can retry and roll back without
double counting.
"""

from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.db.models import Count
from rest_framework import status
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.records.discovery import invalidate_feed
from apps.records.models import Record
from apps.records.serializers import RecordListSerializer
from apps.records.versions import served_manuscript_identity
from core.enums import ReadingStatus

from . import feeds, highlights
from .models import (
    MAX_NOTE_LENGTH,
    MAX_SAVED_FEEDS,
    ReadingHighlight,
    ReadingNote,
    SavedFeed,
    SavedRecord,
)

#: Absent from the body means "leave the status as it is".
_UNSET = object()


def _readable(user):
    return (
        Record.objects.visible_to(user)
        .select_related("classification", "record_type", "ai_overview")
        .prefetch_related("authors")
        .annotate(file_count=Count("files", distinct=True))
    )


def _entry(save, record, context):
    if record is None:
        return {"record_id": save.record_id, "available": False}
    return {
        "record_id": save.record_id,
        "available": True,
        "reading_status": save.reading_status,
        "saved_at": save.saved_at,
        "updated_at": save.updated_at,
        "record": RecordListSerializer(record, context=context).data,
    }


def _reading_status(data):
    if not isinstance(data, dict) or "reading_status" not in data:
        return _UNSET
    value = data["reading_status"]
    if value is None or value == "":
        return None
    if value not in ReadingStatus.values:
        raise ValidationError({"reading_status": [f"Must be one of {', '.join(ReadingStatus.values)}, or null."]})
    return value


class SavedRecordListView(APIView):
    """GET /library/saves/ -- the reader's saves, newest first."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        saves = list(SavedRecord.objects.filter(owner=request.user).order_by("-saved_at", "-pk"))
        records = {r.pk: r for r in _readable(request.user).filter(pk__in=[s.record_id for s in saves])}
        context = {"request": request}
        return Response({"results": [_entry(s, records.get(s.record_id), context) for s in saves]})


class SavedRecordDetailView(APIView):
    """
    PUT /library/saves/<record_id>/ saves the Record, optionally with a
    `reading_status` (one of `ReadingStatus`, or null to clear it).
    DELETE unsaves it; deleting what is not saved is still a 204.
    """

    permission_classes = [IsAuthenticated]

    def put(self, request, record_id):
        reading_status = _reading_status(request.data)
        record = _readable(request.user).filter(pk=record_id).first()
        if record is None:
            raise NotFound()

        with transaction.atomic():
            save, created = SavedRecord.objects.select_for_update().get_or_create(
                owner=request.user,
                record_id=record.pk,
                defaults={"reading_status": None if reading_status is _UNSET else reading_status},
            )
            changed = created
            if not created and reading_status is not _UNSET and save.reading_status != reading_status:
                save.reading_status = reading_status
                save.save(update_fields=["reading_status", "updated_at"])
                changed = True
            if changed:
                # A new save, or a status that moves it within For you (IR-575).
                invalidate_feed(request.user)

        return Response(
            _entry(save, record, {"request": request}),
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )

    def delete(self, request, record_id):
        # No visibility check: removing your own row discloses nothing, and a
        # reader must be able to drop a save that has become unavailable.
        with transaction.atomic():
            deleted, _ = SavedRecord.objects.filter(owner=request.user, record_id=record_id).delete()
            if deleted:
                invalidate_feed(request.user)
        return Response(status=status.HTTP_204_NO_CONTENT)


# -- IR-580: private reading notes (ADR-064) ------------------------------------
#
# The owner is the authenticated user and every queryset starts from
# `ReadingNote.objects.filter(owner=request.user)`, so another reader's note --
# staff's, the Record owner's, anyone's -- cannot be addressed. Every call,
# DELETE included, rechecks `Record.objects.visible_to()`: an unreadable Record
# is the same 404 as a missing one, and the text is kept until access returns.


def _readable_or_404(user, record_id):
    if not Record.objects.visible_to(user).filter(pk=record_id).exists():
        raise NotFound()


def _own_note(user, record_id):
    return ReadingNote.objects.filter(owner=user, record_id=record_id)


def _note_entry(note):
    if note is None:
        return {"body": "", "revision": 0, "updated_at": None}
    return {"body": note.body, "revision": note.revision, "updated_at": note.updated_at}


def _conflict(note):
    return Response(
        {
            "code": "revision_conflict",
            "detail": "This note changed on another device. Your text is kept; reconcile the two.",
            **_note_entry(note),
        },
        status=status.HTTP_409_CONFLICT,
    )


def _note_payload(data):
    """`(body, base_revision)` from a PUT, or a 400. A refused write stores nothing."""
    data = data if isinstance(data, dict) else {}
    body, base = data.get("body"), data.get("base_revision")
    if not isinstance(body, str):
        raise ValidationError({"body": ["Send the note as text."]})
    if isinstance(base, bool) or not isinstance(base, int) or base < 0:
        raise ValidationError({"base_revision": ["Send the revision this edit started from (0 for a new note)."]})
    return body, base


class ReadingNoteView(APIView):
    """
    GET    /library/notes/<record_id>/ -- the reader's note, or an empty one at
           revision 0 (nothing is created by reading).
    PUT    /library/notes/<record_id>/ -- `{body, base_revision}`. Stored only if
           `base_revision` is the stored revision; otherwise a 409 carrying the
           server's `body` and `revision`, and nothing is written.
    DELETE -- removes the note; deleting what is not there is still a 204.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request, record_id):
        _readable_or_404(request.user, record_id)
        return Response(_note_entry(_own_note(request.user, record_id).first()))

    def put(self, request, record_id):
        body, base = _note_payload(request.data)
        if len(body) > MAX_NOTE_LENGTH:
            return Response(
                {
                    "code": "note_too_long",
                    "detail": f"A note holds at most {MAX_NOTE_LENGTH:,} characters.",
                    "max_length": MAX_NOTE_LENGTH,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        _readable_or_404(request.user, record_id)

        with transaction.atomic():
            note = _own_note(request.user, record_id).select_for_update().first()
            if (note.revision if note else 0) != base:
                return _conflict(note)
            if note is None:
                try:
                    with transaction.atomic():
                        note = ReadingNote.objects.create(owner=request.user, record_id=record_id, body=body)
                except IntegrityError:
                    # Another device's first save landed between the read and
                    # the insert; the database's unique rule caught it.
                    return _conflict(_own_note(request.user, record_id).first())
            else:
                note.body = body
                note.revision += 1
                note.save(update_fields=["body", "revision", "updated_at"])

        return Response(_note_entry(note))

    def delete(self, request, record_id):
        # A Record the reader cannot read is a 404 here too (ADR-064 §3), so the
        # endpoint never confirms that a hidden Record exists.
        _readable_or_404(request.user, record_id)
        _own_note(request.user, record_id).delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


# -- IR-583: highlights (ADR-065) -------------------------------------------------
#
# Same two rules as notes. The owner is the authenticated user and every queryset
# starts from `ReadingHighlight.objects.filter(owner=request.user)`; and every
# presentation of a quotation or an anchor rechecks `Record.objects.visible_to()`.
# A third rule is this slice's own: a highlight is bound to the Manuscript bytes
# it was made on. The identity is never taken from the client -- the client only
# says which revision it was shown, and the server refuses the write unless that
# is still what the reader is served.


def _manuscript_conflict(code, detail):
    return Response({"code": code, "detail": detail}, status=status.HTTP_409_CONFLICT)


class HighlightListView(APIView):
    """
    GET /library/highlights/ -- every highlight the reader has saved, newest
    first. A highlight whose Record the reader cannot read is listed as
    `{id, record_id, available: false}` and nothing else (ADR-065 §4).
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        rows = list(ReadingHighlight.objects.filter(owner=request.user).order_by("-created_at", "-pk"))
        readable = {r.pk: r for r in Record.objects.visible_to(request.user).filter(pk__in={h.record_id for h in rows})}
        contexts = {pk: highlights.context_for(record, request.user) for pk, record in readable.items()}
        results = [
            highlights.entry(h, contexts[h.record_id]) if h.record_id in readable else highlights.unavailable(h)
            for h in rows
        ]
        return Response({"results": results})


class RecordHighlightsView(APIView):
    """
    GET  /library/highlights/<record_id>/ -- the reader's highlights on one Record.
    POST /library/highlights/<record_id>/ -- save the passage the reader selected:
         `{manuscript_revision, page, quote, prefix, suffix, regions}`.

    A Record the reader cannot read is the same 404 as a missing one on both.
    `manuscript_revision` is what the reader's own reader showed; it must be the
    revision the server serves them now, else a `409 manuscript_changed` and
    nothing is stored. Saving the same passage again returns the one already there.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request, record_id):
        record = Record.objects.visible_to(request.user).filter(pk=record_id).first()
        if record is None:
            raise NotFound()
        context = highlights.context_for(record, request.user)
        rows = ReadingHighlight.objects.filter(owner=request.user, record=record).order_by("-created_at", "-pk")
        return Response({"results": [highlights.entry(h, context) for h in rows]})

    def post(self, request, record_id):
        fields = highlights.clean(request.data)
        record = Record.objects.visible_to(request.user).filter(pk=record_id).first()
        if record is None:
            raise NotFound()

        revision, sha256 = served_manuscript_identity(record, request.user)
        if revision is None:
            return _manuscript_conflict(
                "manuscript_unavailable", "This paper's Manuscript has no recorded identity, so it cannot be highlighted.",
            )
        if fields["manuscript_revision"] != revision:
            return _manuscript_conflict(
                "manuscript_changed",
                "This paper's Manuscript was replaced while you were reading. Reload it, then select the passage again.",
            )

        with transaction.atomic():
            existing = ReadingHighlight.objects.filter(
                owner=request.user, record=record, manuscript_revision=revision, manuscript_sha256=sha256,
                page=fields["page"], quote=fields["quote"], regions=fields["regions"],
            ).first()
            if existing is not None:
                created, row = False, existing
            else:
                created = True
                row = ReadingHighlight.objects.create(
                    owner=request.user, record=record, manuscript_sha256=sha256, **fields,
                )
        return Response(
            highlights.entry(row, highlights.context_for(record, request.user)),
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )


class HighlightDetailView(APIView):
    """
    DELETE /library/highlights/<record_id>/<highlight_id>/ -- remove one of the
    reader's own. Another reader's, a missing one and one on an unreadable Record
    all answer 204: removing your own row discloses nothing, and a reader must be
    able to drop a highlight whose source they can no longer open (ADR-065 §5).
    """

    permission_classes = [IsAuthenticated]

    def delete(self, request, record_id, highlight_id):
        ReadingHighlight.objects.filter(owner=request.user, record_id=record_id, pk=highlight_id).delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


# -- IR-577: private custom feeds -----------------------------------------------
#
# The owner is the authenticated user, and every queryset starts from
# `SavedFeed.objects.filter(owner=request.user)`: another reader's feed cannot
# be addressed, and answers the same 404 as one that does not exist. A feed is
# not a Record, so no visibility predicate applies; opening one is Discover's
# ordinary list under the reader's own permissions.


def _body(request):
    return request.data if isinstance(request.data, dict) else {}


def _feed_entry(feed, stale):
    return {
        "id": feed.pk,
        "name": feed.name,
        "query": feed.query,
        "stale": stale,
        "created_at": feed.created_at,
        "updated_at": feed.updated_at,
    }


def _locked(user):
    """Serialise one account's feed writes: the limit and the name check both
    count rows, so two simultaneous saves must not both pass them."""
    return get_user_model().objects.select_for_update().get(pk=user.pk)


class SavedFeedListView(APIView):
    """
    GET /library/feeds/ -- the reader's feeds, oldest first, with the limit.
    POST /library/feeds/ -- save one: a name and Discover's query.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        saved = list(SavedFeed.objects.filter(owner=request.user).order_by("created_at", "pk"))
        stale = feeds.stale_values([feed.query for feed in saved])
        return Response({
            "results": [_feed_entry(feed, gone) for feed, gone in zip(saved, stale)],
            "limit": MAX_SAVED_FEEDS,
        })

    def post(self, request):
        data = _body(request)
        name = feeds.clean_name(data.get("name"))
        query = feeds.clean_query(data.get("query"))

        with transaction.atomic():
            _locked(request.user)
            if SavedFeed.objects.filter(owner=request.user).count() >= MAX_SAVED_FEEDS:
                return Response(
                    {
                        "code": "feed_limit",
                        "detail": f"You have {MAX_SAVED_FEEDS} saved feeds. Delete one to save another.",
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )
            if feeds.name_taken(request.user, name):
                raise feeds.duplicate_name()
            try:
                with transaction.atomic():
                    feed = SavedFeed.objects.create(owner=request.user, name=name, query=query)
            except IntegrityError:
                # The database's own case rule caught what the check above missed.
                raise feeds.duplicate_name()

        return Response(_feed_entry(feed, feeds.stale_values([query])[0]), status=status.HTTP_201_CREATED)


class SavedFeedDetailView(APIView):
    """
    PATCH /library/feeds/<id>/ -- rename it, replace its criteria, or both.
    DELETE removes it. A feed that is not the caller's is a 404.

    Renaming never touches the criteria, so a feed with a stale value can still
    be renamed; replacing them re-checks every value, so a stale one has to be
    corrected before it can be saved again.
    """

    permission_classes = [IsAuthenticated]

    def _own(self, request, feed_id):
        feed = SavedFeed.objects.filter(owner=request.user, pk=feed_id).first()
        if feed is None:
            raise NotFound()
        return feed

    def patch(self, request, feed_id):
        data = _body(request)
        if "name" not in data and "query" not in data:
            raise ValidationError({"detail": ["Provide a name or a query to change."]})
        name = feeds.clean_name(data["name"]) if "name" in data else None
        query = feeds.clean_query(data["query"]) if "query" in data else None

        with transaction.atomic():
            _locked(request.user)
            feed = self._own(request, feed_id)
            if name is not None:
                if feeds.name_taken(request.user, name, excluding=feed.pk):
                    raise feeds.duplicate_name()
                feed.name = name
            if query is not None:
                feed.query = query
            try:
                with transaction.atomic():
                    feed.save()
            except IntegrityError:
                raise feeds.duplicate_name()

        return Response(_feed_entry(feed, feeds.stale_values([feed.query])[0]))

    def delete(self, request, feed_id):
        deleted, _ = SavedFeed.objects.filter(owner=request.user, pk=feed_id).delete()
        if not deleted:
            raise NotFound()
        return Response(status=status.HTTP_204_NO_CONTENT)
