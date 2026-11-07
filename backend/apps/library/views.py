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
from core.enums import ReadingStatus

from . import feeds
from .models import MAX_SAVED_FEEDS, SavedFeed, SavedRecord

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
