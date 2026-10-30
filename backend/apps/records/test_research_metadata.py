"""Declared research facts survive the public write/read serializer boundary."""
import pytest

from apps.records.models import Record
from apps.records.serializers import RecordListSerializer, RecordWriteSerializer

pytestmark = [pytest.mark.db_required, pytest.mark.django_db]


def test_declared_origin_and_publication_year_round_trip_without_completion_fallback():
    incoming = RecordWriteSerializer(data={
        "title": "An external reference", "origin": "imported_reference",
        "publication_year": 2017, "year_accomplished": 2023,
    })
    assert incoming.is_valid(), incoming.errors
    record = incoming.save()
    outgoing = RecordListSerializer(record).data
    assert outgoing["origin"] == "imported_reference"
    assert outgoing["publication_year"] == 2017
    assert outgoing["year_accomplished"] == 2023
    unknown = Record.objects.create(title="Unclassified legacy research", year_accomplished=2020)
    assert RecordListSerializer(unknown).data["origin"] == "unknown"
    assert RecordListSerializer(unknown).data["publication_year"] is None


def test_invalid_declared_origin_is_rejected():
    incoming = RecordWriteSerializer(data={"title": "Reference", "origin": "guessed"})
    assert not incoming.is_valid()
    assert "origin" in incoming.errors


def test_origin_does_not_grant_metadata_edit_permission():
    from rest_framework.test import APIClient
    from django.urls import reverse
    from apps.records.tests import make_user
    from apps.records.models import RecordOwner
    owner = make_user("metadata-owner@cit.edu", "Student")
    other = make_user("metadata-other@cit.edu", "RDCO")
    record = Record.objects.create(title="Owned draft", added_by=owner)
    RecordOwner.objects.create(record=record, user=owner, is_primary=True)
    client = APIClient()
    client.force_authenticate(other)
    response = client.patch(reverse("record-detail", args=[record.pk]), {"origin": "institutional"}, format="json")
    assert response.status_code == 403
    client.force_authenticate(owner)
    response = client.patch(reverse("record-detail", args=[record.pk]), {"origin": "imported_reference", "publication_year": 2017}, format="json")
    assert response.status_code == 200, response.data
    record.refresh_from_db()
    assert record.origin == "imported_reference"
