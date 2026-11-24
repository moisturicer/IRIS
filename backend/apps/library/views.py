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
from django.utils import timezone
from rest_framework import status
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.records.discovery import invalidate_feed
from apps.records.models import Record
from apps.records.serializers import RecordListSerializer
from apps.records.versions import served_manuscript_identity
from core.enums import PipelineStatus, ReadingStatus

from . import feeds, folders, highlights, positions
from .models import (
    MAX_FOLDERS,
    MAX_HISTORY_ENTRIES,
    MAX_NOTE_LENGTH,
    MAX_SAVED_FEEDS,
    FolderMembership,
    LibraryFolder,
    LibraryPreferences,
    ReadingHighlight,
    ReadingNote,
    ReadingVisit,
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
    DELETE unsaves it, which takes it out of every folder too (IR-572);
    deleting what is not saved is still a 204.
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
# DELETE included, rechecks `annotatable()`: an unreadable or unpublished Record
# is the same 404 as a missing one, and the text is kept until it returns.


def annotatable(user):
    """
    The Records `user` may keep notes and highlights on: the ones they may read
    that are published (ADR-064 and ADR-065 as amended 2026-11-24, IR-1326).
    A draft or a paper in review has review comments instead, and a note or
    highlight on one is withheld, not deleted, until it is published.
    """
    return Record.objects.visible_to(user).filter(pipeline_status=PipelineStatus.PUBLISHED)


def _readable_or_404(user, record_id):
    """The Record, if `user` may read it; else the same 404 as a missing one."""
    record = Record.objects.visible_to(user).filter(pk=record_id).first()
    if record is None:
        raise NotFound()
    return record


def _annotatable_or_404(user, record_id):
    """The Record, if `user` may keep notes or highlights on it; else the 404 of a missing one."""
    record = annotatable(user).filter(pk=record_id).first()
    if record is None:
        raise NotFound()
    return record


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
        _annotatable_or_404(request.user, record_id)
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
        _annotatable_or_404(request.user, record_id)

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
        _annotatable_or_404(request.user, record_id)
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
    `{id, record_id, available: false}` and nothing else (ADR-065 §4), and so
    is one on a paper that isn't published (IR-1326).
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        rows = list(ReadingHighlight.objects.filter(owner=request.user).order_by("-created_at", "-pk"))
        readable = {r.pk: r for r in annotatable(request.user).filter(pk__in={h.record_id for h in rows})}
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

    A Record the reader cannot read, or one not published (IR-1326), is the
    same 404 as a missing one on both.
    `manuscript_revision` is what the reader's own reader showed; it must be the
    revision the server serves them now, else a `409 manuscript_changed` and
    nothing is stored. Saving the same passage again returns the one already there.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request, record_id):
        record = _annotatable_or_404(request.user, record_id)
        context = highlights.context_for(record, request.user)
        rows = ReadingHighlight.objects.filter(owner=request.user, record=record).order_by("-created_at", "-pk")
        return Response({"results": [highlights.entry(h, context) for h in rows]})

    def post(self, request, record_id):
        fields = highlights.clean(request.data)
        record = _annotatable_or_404(request.user, record_id)

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
    """Serialise one account's feed or folder writes: the limit and the name
    check both count rows, so two simultaneous saves must not both pass them."""
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


# -- IR-572: the reader's own folders (ADR-070) ----------------------------------
#
# The owner is the authenticated user, and every queryset starts from
# `LibraryFolder.objects.filter(owner=request.user)`: another reader's folder
# cannot be addressed, and answers the same 404 as one that does not exist.
# Filing a Record rechecks `Record.objects.visible_to()` and saves it, because a
# folder holds saved papers. Nothing here is a discovery signal: no folder write
# invalidates For you or touches "Not interested".


class FolderListView(APIView):
    """
    GET  /library/folders/ -- the reader's folders, oldest first, each with the
         ids of the Records filed in it (newest first), and the account limit.
    POST /library/folders/ -- create one by name. Creating a name the reader
         already has, ignoring case, returns that folder with a 200, so a retry
         or a second click never makes two.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        own = LibraryFolder.objects.filter(owner=request.user).order_by("created_at", "pk")
        return Response({"results": folders.entries(own), "limit": MAX_FOLDERS})

    def post(self, request):
        name = folders.clean_name(_body(request).get("name"))

        with transaction.atomic():
            _locked(request.user)
            existing = folders.folder_named(request.user, name)
            if existing is not None:
                return Response(folders.entry(existing), status=status.HTTP_200_OK)
            if LibraryFolder.objects.filter(owner=request.user).count() >= MAX_FOLDERS:
                return Response(
                    {
                        "code": "folder_limit",
                        "detail": f"You have {MAX_FOLDERS} folders. Delete one to make another.",
                        "limit": MAX_FOLDERS,
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )
            folder = LibraryFolder.objects.create(owner=request.user, name=name)

        return Response(folders.entry(folder), status=status.HTTP_201_CREATED)


class FolderDetailView(APIView):
    """
    PATCH  /library/folders/<id>/ -- rename it. Renaming to its own name, in
           any case, is a 200; to another of the reader's folders' names, a 400.
    DELETE /library/folders/<id>/ -- remove it and its filings, never a save.
           Deleting what is not there, or is not the caller's, is still a 204:
           it removes nothing and discloses nothing.
    """

    permission_classes = [IsAuthenticated]

    def patch(self, request, folder_id):
        name = folders.clean_name(_body(request).get("name"))

        with transaction.atomic():
            _locked(request.user)
            folder = LibraryFolder.objects.filter(owner=request.user, pk=folder_id).first()
            if folder is None:
                raise NotFound()
            if folders.folder_named(request.user, name, excluding=folder.pk) is not None:
                raise folders.duplicate_name()
            if folder.name != name:
                folder.name = name
                folder.save(update_fields=["name", "updated_at"])

        return Response(folders.entry(folder))

    def delete(self, request, folder_id):
        LibraryFolder.objects.filter(owner=request.user, pk=folder_id).delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class FolderRecordView(APIView):
    """
    PUT    /library/folders/<id>/records/<record_id>/ -- file a Record in one
           of the reader's folders. A folder holds saved papers, so an unsaved
           Record is saved first, with no Reading status. Repeating it changes
           nothing. Answers the folder and the save.
    DELETE -- take it out of that folder. The save, its status and every other
           folder are untouched, and it is not "Not interested". Removing what
           is not there is still a 204, with no visibility check, so a reader
           can tidy away a Record they can no longer read.

    A folder that is not the caller's, and a Record they cannot read, are each
    the same 404 as a missing one, and nothing is written.
    """

    permission_classes = [IsAuthenticated]

    def put(self, request, folder_id, record_id):
        with transaction.atomic():
            folder = LibraryFolder.objects.select_for_update().filter(owner=request.user, pk=folder_id).first()
            if folder is None:
                raise NotFound()
            record = _readable(request.user).filter(pk=record_id).first()
            if record is None:
                raise NotFound()
            # Locked, so an unsave arriving now waits for this filing and then
            # cascades it away, rather than leaving a filing with no save.
            save, saved_now = SavedRecord.objects.select_for_update().get_or_create(
                owner=request.user, record_id=record.pk,
            )
            if saved_now:
                # A new save is a For you signal (IR-575); the filing is not.
                invalidate_feed(request.user)
            _, filed = FolderMembership.objects.get_or_create(folder=folder, saved_record=save)

        return Response(
            {"folder": folders.entry(folder), "save": _entry(save, record, {"request": request})},
            status=status.HTTP_201_CREATED if filed else status.HTTP_200_OK,
        )

    def delete(self, request, folder_id, record_id):
        FolderMembership.objects.filter(
            folder__owner=request.user, folder_id=folder_id, saved_record__record_id=record_id,
        ).delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


# -- IR-756: reading history (ADR-044 §Amendment 2026-11-01) ---------------------
#
# The owner is the authenticated user and every queryset starts from
# `ReadingVisit.objects.filter(owner=request.user)`; no staff route exists. A
# visit is recorded only by the paper view's explicit PUT, never by reading a
# Record, and every list rechecks `Record.objects.visible_to()`.


def _visit_entry(visit, record, context):
    if record is None:
        return {"record_id": visit.record_id, "available": False}
    return {
        "record_id": visit.record_id,
        "available": True,
        "viewed_at": visit.viewed_at,
        "record": RecordListSerializer(record, context=context).data,
    }


class ReadingHistoryView(APIView):
    """
    GET /library/history/ -- the papers the reader opened, most recent first.
    DELETE clears it.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        visits = list(ReadingVisit.objects.filter(owner=request.user).order_by("-viewed_at", "-pk"))
        records = {r.pk: r for r in _readable(request.user).filter(pk__in=[v.record_id for v in visits])}
        context = {"request": request}
        return Response({"results": [_visit_entry(v, records.get(v.record_id), context) for v in visits]})

    def delete(self, request):
        """Clear history: the rows are deleted, not hidden."""
        ReadingVisit.objects.filter(owner=request.user).delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class ReadingHistoryRemoveView(APIView):
    """
    POST /library/history/remove/ -- `{"record_ids": [1, 2]}` deletes those
    papers from the caller's history, in one transaction (IR-1331). Only the
    caller's own rows are touched, so an id that is not in their history, or a
    Record they can no longer read, is simply removed or skipped: the answer is
    the same 204 and discloses nothing. The ids must be a non-empty list of
    integers, no longer than the history can hold, so a mistake never reads as
    "clear everything".
    """

    permission_classes = [IsAuthenticated]

    def post(self, request):
        ids = _body(request).get("record_ids")
        valid = (
            isinstance(ids, list)
            and 0 < len(ids) <= MAX_HISTORY_ENTRIES
            and all(isinstance(i, int) and not isinstance(i, bool) for i in ids)
        )
        if not valid:
            raise ValidationError({"record_ids": [
                f"Send a list of 1 to {MAX_HISTORY_ENTRIES} paper ids to remove from your history.",
            ]})
        ReadingVisit.objects.filter(owner=request.user, record_id__in=ids).delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class ReadingVisitView(APIView):
    """
    PUT /library/history/<record_id>/ -- the paper view says the reader opened
    this Record. Idempotent: a revisit moves it to the top. A Record the reader
    cannot read is the same 404 as a missing one. While history is paused the
    answer is the same 204 and nothing is written, not even `viewed_at`.
    """

    permission_classes = [IsAuthenticated]

    def put(self, request, record_id):
        _readable_or_404(request.user, record_id)
        if not LibraryPreferences.keeps_history(request.user):
            return Response(status=status.HTTP_204_NO_CONTENT)
        with transaction.atomic():
            ReadingVisit.objects.update_or_create(
                owner=request.user, record_id=record_id, defaults={"viewed_at": timezone.now()},
            )
            stale = ReadingVisit.objects.filter(owner=request.user).order_by("-viewed_at", "-pk")[MAX_HISTORY_ENTRIES:]
            ReadingVisit.objects.filter(pk__in=list(stale.values_list("pk", flat=True))).delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class LibraryPreferencesView(APIView):
    """
    GET   /library/preferences/ -- the reader's settings; defaults when none is
          stored, and reading creates nothing.
    PATCH /library/preferences/ -- `{"keep_history": true|false}`. Off pauses
          reading history (ADR-044 §Amendment 2026-11-01, point 7).
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response({"keep_history": LibraryPreferences.keeps_history(request.user)})

    def patch(self, request):
        value = _body(request).get("keep_history")
        if not isinstance(value, bool):
            raise ValidationError({"keep_history": ["Send true to keep reading history or false to pause it."]})
        LibraryPreferences.objects.update_or_create(owner=request.user, defaults={"keep_history": value})
        return Response({"keep_history": value})


# -- IR-573: resume reading ------------------------------------------------------
#
# The rules of notes and highlights. The owner is the authenticated user and
# every query starts from the reader's own row; a Record they cannot read is the
# same 404 as a missing one on both read and write. And the place is bound to
# the Manuscript bytes it was read on: the client only says which revision it
# was shown, and the server refuses the write unless that is still what the
# reader is served (`positions`).


class ReadingPositionView(APIView):
    """
    GET /library/positions/<record_id>/ -- `{position: {page, fraction,
        manuscript_revision, updated_at}}`, or `{position: null}` when the reader
        has none on the bytes they are served now. Reading never creates a
        place; it deletes one left on bytes the reader is no longer served.
    PUT /library/positions/<record_id>/ -- `{manuscript_revision, page, fraction}`,
        saved by the paper view as the reader moves. 204; a `409 manuscript_changed`
        when the revision is no longer the one served, and nothing is stored.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request, record_id):
        row = positions.current(request.user, _readable_or_404(request.user, record_id))
        if row is None:
            return Response({"position": None})
        return Response({"position": {
            "page": row.page,
            "fraction": row.fraction,
            "manuscript_revision": str(row.manuscript_revision),
            "updated_at": row.updated_at,
        }})

    def put(self, request, record_id):
        fields = positions.clean(request.data)
        _readable_or_404(request.user, record_id)
        with transaction.atomic():
            # The Record's row is held until the place is stored, so an upload
            # replacing these bytes waits, and its receiver then deletes it.
            record = Record.objects.select_for_update().get(pk=record_id)
            revision, sha256 = served_manuscript_identity(record, request.user)
            if revision is None:
                return _manuscript_conflict(
                    "manuscript_unavailable", "This paper's Manuscript has no recorded identity, so no place is kept in it.",
                )
            if fields["manuscript_revision"] != revision:
                return _manuscript_conflict(
                    "manuscript_changed", "This paper's Manuscript was replaced while you were reading it.",
                )
            positions.save(request.user, record, (revision, sha256), page=fields["page"], fraction=fields["fraction"])
        return Response(status=status.HTTP_204_NO_CONTENT)
