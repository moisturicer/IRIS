"""Owner-scoped metadata discovery: IR-567, IR-575's saved-Area signal, and IR-576's feedback and reset."""

from collections import deque
from datetime import timedelta

from django.core import signing
from django.db import transaction
from django.db.models import Count
from django.utils import timezone
from rest_framework import status
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from apps.library.models import SavedRecord
from core.enums import PUBLICLY_VISIBLE_STATUSES

from .models import (
    Classification, DiscoveryDismissal, DiscoveryFeedSnapshot, DiscoveryInterests,
    PSCEDClassification, Record,
)
from .filters import RecordFilter
from .serializers import RecordListSerializer


PAGE_SIZE = 20
# 2: saved Records' Areas join the chosen ones (IR-575); entries gain a `source`.
RECIPE_VERSION = 2
CURSOR_SALT = "records.discovery.v1"
SNAPSHOT_AGE = 24 * 60 * 60
FILTER_KEYS = (
    "record_type", "college", "classification", "year_from", "year_to",
    "is_ip", "ip_type",
)


def _interests(user):
    return DiscoveryInterests.objects.get_or_create(user=user)[0]


def _interests_payload(interests):
    return {
        "classifications": list(interests.classifications.order_by("id").values("id", "name")),
        "psced": list(interests.psced.order_by("id").values("id", "name")),
    }


def get_interests(user):
    return Response(_interests_payload(_interests(user)))


def _validated_ids(data, field, model):
    values = data.get(field)
    if not isinstance(values, list) or any(type(value) is not int or value <= 0 for value in values):
        raise ValidationError({field: "Provide a list of Area IDs."})
    ids = set(values)
    if model.objects.filter(pk__in=ids).count() != len(ids):
        raise ValidationError({field: "An Area is unknown. Refresh the choices."})
    return ids


@transaction.atomic
def put_interests(user, data):
    classification_ids = _validated_ids(data, "classification_ids", Classification)
    psced_ids = _validated_ids(data, "psced_ids", PSCEDClassification)
    interests = _locked_interests(user)
    if (
        set(interests.classifications.values_list("pk", flat=True)) != classification_ids
        or set(interests.psced.values_list("pk", flat=True)) != psced_ids
    ):
        interests.classifications.set(classification_ids)
        interests.psced.set(psced_ids)
        _invalidate(interests)
    return Response(_interests_payload(interests))


def _invalidate(interests):
    """Bump the revision: every outstanding cursor goes stale (409), and the
    next feed is a fresh snapshot."""
    interests.revision += 1
    interests.save(update_fields=["revision"])


def _locked_interests(user):
    return DiscoveryInterests.objects.select_for_update().get(pk=_interests(user).pk)


def invalidate_feed(user):
    """The reader's saves changed, so every outstanding cursor goes stale (409).

    Called by the library inside the same transaction as the save it follows.
    Serialised with interest edits and resets by the same row lock.
    """
    _invalidate(_locked_interests(user))


def _saved_areas(user):
    """Areas of the Records the reader has saved *and may still read* (IR-575).

    The one visibility predicate and the published-catalogue rule apply here
    exactly as they do to candidates, so a save the reader lost access to
    stops being a signal. A dismissal does not remove it: unsaving and
    "Not interested" are independent. A Record with no Area adds nothing.
    """
    saved = (
        Record.objects.visible_to(user)
        .filter(
            pipeline_status__in=PUBLICLY_VISIBLE_STATUSES,
            pk__in=SavedRecord.objects.filter(owner=user).values("record_id"),
        )
        .values_list("classification_id", "psced_id")
    )
    areas = set()
    for classification_id, psced_id in saved:
        if classification_id is not None:
            areas.add(("classification", classification_id))
        if psced_id is not None:
            areas.add(("psced", psced_id))
    return areas


@transaction.atomic
def reset_interests(user):
    """Clear chosen Areas and every Not interested. Saved papers are not feedback."""
    interests = _locked_interests(user)
    interests.classifications.clear()
    interests.psced.clear()
    DiscoveryDismissal.objects.filter(user=user).delete()
    DiscoveryFeedSnapshot.objects.filter(user=user).delete()
    _invalidate(interests)
    return Response(_interests_payload(interests))


@transaction.atomic
def dismiss(user, record):
    """Not interested. Pages already frozen drop it too, so cursors stay valid:
    removing an item reorders nothing, so the revision is left alone."""
    _locked_interests(user)  # Serialised with a reset, which would otherwise miss it.
    _, created = DiscoveryDismissal.objects.get_or_create(user=user, record=record)
    return Response(status=status.HTTP_201_CREATED if created else status.HTTP_200_OK)


@transaction.atomic
def undo_dismissal(user, record_id):
    """Undo restores the Record under a fresh snapshot, not into an old one."""
    interests = _locked_interests(user)
    deleted, _ = DiscoveryDismissal.objects.filter(user=user, record_id=record_id).delete()
    if deleted:
        _invalidate(interests)
    return Response(status=status.HTTP_204_NO_CONTENT)


def _catalogue(user, filters=None):
    queryset = (
        Record.objects.visible_to(user)
        .filter(pipeline_status__in=PUBLICLY_VISIBLE_STATUSES)
        .select_related("classification", "psced", "record_type", "ai_overview")
        .prefetch_related("authors")
        .annotate(file_count=Count("files", distinct=True))
        .exclude(pk__in=DiscoveryDismissal.objects.filter(user=user).values("record_id"))
        .order_by("-created_at", "-pk")
    )
    if filters:
        filtered = RecordFilter(filters, queryset=queryset)
        if not filtered.is_valid():
            raise ValidationError(filtered.errors)
        return filtered.qs.order_by("-created_at", "-pk")
    return queryset


def _ordered_entries(records, interests, saved_areas, saved_ids):
    """Metadata recipe v2 (IR-567, IR-575).

    The interest Areas are the reader's chosen ones plus the Areas of
    currently readable saved Records. Within an Area, Records the reader has
    not saved come before ones they have (a completed Record is a saved one),
    each group keeping added-date order, so older research stays eligible.
    An entry says which kind of input put it there: a chosen Area wins over a
    saved one, so the reason names what the reader actually did.
    """
    chosen = {
        ("classification", area_id)
        for area_id in interests.classifications.values_list("id", flat=True)
    } | {
        ("psced", area_id)
        for area_id in interests.psced.values_list("id", flat=True)
    }
    selected = sorted(chosen | saved_areas, key=lambda area: (area[1], area[0]))
    buckets = []
    for kind, area_id in selected:
        matching = [record for record in records if getattr(record, f"{kind}_id") == area_id]
        buckets.append(deque(
            [record for record in matching if record.pk not in saved_ids]
            + [record for record in matching if record.pk in saved_ids]
        ))
    entries = []
    seen = set()
    while any(buckets):
        for area, bucket in zip(selected, buckets):
            if not bucket:
                continue
            record = bucket.popleft()
            if record.pk not in seen:
                entries.append({
                    "id": record.pk, "area_type": area[0], "area_id": area[1],
                    "source": "selected" if area in chosen else "saved",
                })
                seen.add(record.pk)
    mode = "for_you" if entries else "latest"
    entries.extend({"id": record.pk} for record in records if record.pk not in seen)
    return mode, entries


def _cursor(snapshot, offset, filters):
    return signing.dumps(
        {"snapshot": str(snapshot.pk), "owner": snapshot.user_id, "offset": offset, "filters": filters},
        salt=CURSOR_SALT, compress=True,
    )


def _stale():
    return Response(
        {"code": "stale_cursor", "detail": "This feed changed. Refresh it to continue."},
        status=status.HTTP_409_CONFLICT,
    )


def get_feed(request):
    interests = _interests(request.user)
    token = request.query_params.get("cursor")
    if token:
        try:
            cursor = signing.loads(token, salt=CURSOR_SALT, max_age=SNAPSHOT_AGE)
            if cursor["owner"] != request.user.pk or type(cursor["offset"]) is not int:
                raise ValueError
            offset = cursor["offset"]
            filters = cursor["filters"]
            if offset < 0 or not isinstance(filters, dict):
                raise ValueError
        except signing.SignatureExpired:
            return _stale()
        except (signing.BadSignature, KeyError, TypeError, ValueError):
            return Response({"detail": "Invalid feed cursor."}, status=status.HTTP_400_BAD_REQUEST)
        snapshot = DiscoveryFeedSnapshot.objects.filter(
            pk=cursor["snapshot"], user=request.user,
        ).first()
        if (
            snapshot is None
            or snapshot.interest_revision != interests.revision
            or snapshot.recipe_version != RECIPE_VERSION
        ):
            return _stale()
    else:
        filters = {key: request.query_params[key] for key in FILTER_KEYS if key in request.query_params}
        records = list(_catalogue(request.user, filters))
        mode, entries = _ordered_entries(
            records, interests, _saved_areas(request.user),
            set(SavedRecord.objects.filter(owner=request.user).values_list("record_id", flat=True)),
        )
        snapshot = DiscoveryFeedSnapshot.objects.create(
            user=request.user, interest_revision=interests.revision,
            recipe_version=RECIPE_VERSION, mode=mode, entries=entries,
        )
        DiscoveryFeedSnapshot.objects.filter(
            user=request.user, created_at__lt=timezone.now() - timedelta(seconds=SNAPSHOT_AGE)
        ).delete()
        offset = 0

    entries = snapshot.entries
    # The snapshot fixes order, not access. A withdrawn or deleted Record is
    # absent even when its ID was saved on an earlier page.
    live = {
        record.pk: record
        for record in _catalogue(request.user, filters).filter(pk__in=[entry["id"] for entry in entries])
    }

    def current(entry):
        record = live.get(entry["id"])
        if record is None:
            return False
        kind = entry.get("area_type")
        return kind is None or getattr(record, f"{kind}_id") == entry["area_id"]

    valid = [entry for entry in entries[offset:] if current(entry)]
    page_entries = valid[:PAGE_SIZE]
    if len(valid) > PAGE_SIZE:
        last_id = page_entries[-1]["id"]
        next_offset = next(
            index + 1 for index in range(offset, len(entries))
            if entries[index]["id"] == last_id
        )
        next_cursor = _cursor(snapshot, next_offset, filters)
    else:
        next_cursor = None

    # The snapshot also froze which Areas were saved-sourced. A reason may only
    # name a signal the reader can still read, so a saved Area whose Records
    # were withdrawn since is no longer named; the item stays where it is.
    saved_areas = _saved_areas(request.user) if any(
        entry.get("source") == "saved" for entry in page_entries
    ) else set()
    rows = []
    for entry in page_entries:
        record = live[entry["id"]]
        row = dict(RecordListSerializer(record, context={"request": request}).data)
        kind = entry.get("area_type")
        if kind and entry.get("source") == "saved":
            named = (kind, entry["area_id"]) in saved_areas
            row["reason"] = (
                {"kind": "saved_area", "area": getattr(record, kind).name}
                if named else {"kind": "latest"}
            )
        elif kind:
            row["reason"] = {"kind": "selected_area", "area": getattr(record, kind).name}
        else:
            row["reason"] = {"kind": "latest"}
        rows.append(row)
    return Response({
        "mode": snapshot.mode,
        "results": rows,
        "next_cursor": next_cursor,
        "count": sum(current(entry) for entry in entries),
    })
