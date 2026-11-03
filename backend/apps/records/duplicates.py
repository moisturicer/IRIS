"""Readable Manuscript matches at the attachment and submission boundaries."""
import hashlib
import json
import unicodedata

from django.db import connection
from rest_framework.exceptions import APIException
from core.enums import PipelineStatus

from .models import Record


POLICY_VERSION = 1


class ExactDuplicate(APIException):
    status_code = 409
    default_code = "exact_duplicate"

    def __init__(self, matches):
        self.detail = {
            "code": "exact_duplicate",
            "detail": "This manuscript is already attached to a record you can read.",
            "matches": matches,
        }


def lock_digest(digest):
    """Transaction-scoped PostgreSQL lock shared by upload and submit writers."""
    if not digest:
        return
    key = int.from_bytes(bytes.fromhex(digest)[:8], "big", signed=True)
    with connection.cursor() as cursor:
        cursor.execute("SELECT pg_advisory_xact_lock(%s)", [key])


def _link(record, user):
    owned_draft = record.pipeline_status == PipelineStatus.DRAFT and record.owners.filter(user=user).exists()
    return {
        "id": record.pk, "title": record.title,
        "url": f"/records/{record.pk}",
        "action": "resume_draft" if owned_draft else "open_record",
    }


def exact_matches(user, record_id, digest):
    if not digest:
        return []
    # Visibility is applied in SQL before any row is returned or counted.
    records = Record.objects.visible_to(user).filter(manuscript_sha256=digest).exclude(pk=record_id).order_by("pk")
    return [_link(record, user) for record in records[:20]]


def enforce_exact(user, record_id, digest):
    matches = exact_matches(user, record_id, digest)
    if matches:
        raise ExactDuplicate(matches)


def normalize(value):
    text = unicodedata.normalize("NFKC", value or "").casefold()
    return " ".join("".join(char if char.isalnum() else " " for char in text).split())


def _authors(record):
    return {normalize(name) for name in record.authors.values_list("name", flat=True)} - {""}


def likely_matches(user, record):
    title = normalize(record.title)
    if not title:
        return []
    tokens = set(title.split())
    authors = _authors(record)
    found = []
    for candidate in Record.objects.visible_to(user).exclude(pk=record.pk).prefetch_related("authors"):
        other = normalize(candidate.title)
        if not other:
            continue
        other_tokens = set(other.split())
        similarity = len(tokens & other_tokens) / len(tokens | other_tokens)
        overlap = len(authors & _authors(candidate))
        exact = title == other
        if exact or (similarity >= 0.8 and overlap):
            found.append((not exact, -similarity, -overlap, candidate.pk, candidate,
                          "same_title" if exact else "similar_title_and_author"))
    found.sort(key=lambda row: row[:4])
    return [{**_link(candidate, user), "reason": reason} for _, _, _, _, candidate, reason in found[:5]]


def acknowledgement_basis(record, matches):
    value = [POLICY_VERSION, str(record.manuscript_revision), normalize(record.title),
             sorted(_authors(record)), sorted(item["id"] for item in matches)]
    return hashlib.sha256(json.dumps(value, ensure_ascii=False).encode()).hexdigest()
