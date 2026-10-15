"""Owner-scoped metadata discovery for IR-567."""

from collections import deque
from datetime import timedelta

from django.core import signing
from django.db import transaction
from django.db.models import Count
from django.utils import timezone
from rest_framework import status
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from core.enums import PUBLICLY_VISIBLE_STATUSES

from .models import (
    Classification, DiscoveryFeedSnapshot, DiscoveryInterests,
    PSCEDClassification, Record,
)
from .filters import RecordFilter
from .serializers import RecordListSerializer


PAGE_SIZE = 20
RECIPE_VERSION = 1
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
    interests = _interests(user)
    interests = DiscoveryInterests.objects.select_for_update().get(pk=interests.pk)
    if (
        set(interests.classifications.values_list("pk", flat=True)) != classification_ids
        or set(interests.psced.values_list("pk", flat=True)) != psced_ids
    ):
        interests.classifications.set(classification_ids)
        interests.psced.set(psced_ids)
        interests.revision += 1
        interests.save(update_fields=["revision"])
    return Response(_interests_payload(interests))


def _catalogue(user, filters=None):
    queryset = (
        Record.objects.visible_to(user)
        .filter(pipeline_status__in=PUBLICLY_VISIBLE_STATUSES)
        .select_related("classification", "psced", "record_type")
        .prefetch_related("authors")
        .annotate(file_count=Count("files", distinct=True))
        .order_by("-created_at", "-pk")
    )
    if filters:
        filtered = RecordFilter(filters, queryset=queryset)
        if not filtered.is_valid():
            raise ValidationError(filtered.errors)
        return filtered.qs.order_by("-created_at", "-pk")
    return queryset


def _ordered_entries(records, interests):
    selected = [
        ("classification", area_id)
        for area_id in interests.classifications.order_by("id").values_list("id", flat=True)
    ] + [
        ("psced", area_id)
        for area_id in interests.psced.order_by("id").values_list("id", flat=True)
    ]
    selected.sort(key=lambda area: (area[1], area[0]))
    buckets = [
        deque(record for record in records if getattr(record, f"{kind}_id") == area_id)
        for kind, area_id in selected
    ]
    entries = []
    seen = set()
    while any(buckets):
        for (kind, area_id), bucket in zip(selected, buckets):
            if not bucket:
                continue
            record = bucket.popleft()
            if record.pk not in seen:
                entries.append({"id": record.pk, "area_type": kind, "area_id": area_id})
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
        mode, entries = _ordered_entries(records, interests)
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

    rows = []
    for entry in page_entries:
        record = live[entry["id"]]
        row = dict(RecordListSerializer(record, context={"request": request}).data)
        kind = entry.get("area_type")
        row["reason"] = (
            {"kind": "selected_area", "area": getattr(record, kind).name}
            if kind else {"kind": "latest"}
        )
        rows.append(row)
    return Response({
        "mode": snapshot.mode,
        "results": rows,
        "next_cursor": next_cursor,
        "count": sum(current(entry) for entry in entries),
    })
