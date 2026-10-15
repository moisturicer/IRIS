"""
`GET /records/facets/` -- the filter choices Discover offers (IR-560).

Discover's Year menu used to be built from the cards loaded so far, so a year
held only by Records beyond the first page was never offered and those Records
could not be reached by filtering. The choices now come from the whole
catalogue Discover lists: `visible_to(user)` narrowed to the public statuses,
the same queryset as `list`.

The years are `year_accomplished`, the field the `year_from`/`year_to` filters
read, so every offered year returns at least one Record.

**Seam: the records API.**
"""

from rest_framework import status
from rest_framework.test import APITestCase

from apps.accounts.models import Role, User
from apps.records.models import Record, RecordOwner, RecordType
from core.enums import PipelineStatus, RecordTypeName, RoleName

FACETS = "/api/v1/records/facets/"


def _user(email, role_name):
    # Roles are seeded by migration with explicit keys; create() would collide.
    role = Role.objects.get_or_create(name=role_name)[0]
    return User.objects.create_user(
        email=email, password="TestPass123!", first_name="Test",
        last_name="User", role=role, is_verified=True,
    )


class CatalogueFacetTests(APITestCase):

    @classmethod
    def setUpTestData(cls):
        cls.reader = _user("facet-reader@cit.edu", RoleName.STUDENT)
        cls.owner = _user("facet-owner@cit.edu", RoleName.STUDENT)
        cls.rdco = _user("facet-rdco@cit.edu", RoleName.RDCO)
        cls.thesis = RecordType.objects.get(name=RecordTypeName.THESIS_RESEARCH)

    def record(self, year, pipeline_status=PipelineStatus.PUBLISHED, owner=None):
        record = Record.objects.create(
            title=f"Facet fixture {year} {pipeline_status}",
            abstract="An abstract.",
            record_type=self.thesis,
            added_by=owner or self.owner,
            pipeline_status=pipeline_status,
            year_accomplished=year,
        )
        RecordOwner.objects.create(record=record, user=owner or self.owner, is_primary=True)
        return record

    def facets(self, viewer):
        self.client.force_authenticate(viewer)
        response = self.client.get(FACETS)
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        return response.data

    def test_years_come_from_the_whole_catalogue_newest_first(self):
        # Thirteen Records in 2026 fill Discover's first page (12); 2009 sits
        # beyond it and must still be offered.
        for _ in range(13):
            self.record(2026)
        self.record(2009)
        self.record(2018)
        self.record(2018)

        self.assertEqual(self.facets(self.reader)["years"], [2026, 2018, 2009])

    def test_a_record_with_no_year_offers_no_year(self):
        self.record(None)
        self.record(2020)

        self.assertEqual(self.facets(self.reader)["years"], [2020])

    def test_only_the_public_catalogue_contributes(self):
        self.record(2021)
        for hidden in (PipelineStatus.DRAFT, PipelineStatus.IN_REVIEW,
                       PipelineStatus.REJECTED, PipelineStatus.PENDING_DELETE):
            self.record(1999, pipeline_status=hidden)

        # Not even to someone entitled to read the unpublished rows: Discover
        # is a catalogue, and these choices are the catalogue's (ADR-021 §13).
        for viewer in (self.reader, self.owner, self.rdco):
            with self.subTest(viewer=viewer.email):
                self.assertEqual(self.facets(viewer)["years"], [2021])

    def test_an_empty_catalogue_offers_no_years(self):
        self.assertEqual(self.facets(self.reader)["years"], [])

    def test_anonymous_is_refused(self):
        self.client.force_authenticate(None)
        response = self.client.get(FACETS)
        self.assertIn(
            response.status_code,
            (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN),
        )
