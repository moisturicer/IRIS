"""
`GET /records/facets/` -- the filter choices Discover offers (IR-560).

Discover's Year menu used to be built from the cards loaded so far, so a year
held only by Records beyond the first page was never offered and those Records
could not be reached by filtering. The choices now come from the whole
catalogue Discover lists: `visible_to(user)` narrowed to the public statuses,
the same queryset as `list`.

The years are the completion year the `year_from`/`year_to` filters
read (IR-1316), so every offered year returns at least one Record.

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


class OneCompletionYearTests(APITestCase):
    """The form's year and an import's are one completion year in Discover (IR-1316)."""

    def setUp(self):
        self.client.force_authenticate(_user("one-year@cit.edu", RoleName.STUDENT))
        self.form, self.imported, self.both, self.blank = (
            Record.objects.create(title=title, abstract="", pipeline_status=PipelineStatus.PUBLISHED, **years)
            for title, years in (
                ("Form", {"year_accomplished": 2024}), ("Import", {"year_completed": 2022}),
                ("Both", {"year_accomplished": 2020, "year_completed": 2021}), ("Blank", {})))

    def titles(self, **params):
        body = self.client.get("/api/v1/records/", params).json()
        return [row["title"] for row in body["results"]]

    def test_the_year_filter_and_facets_read_either_field(self):
        self.assertEqual(set(self.titles(year_from=2022)), {"Form", "Import"})
        self.assertEqual(self.titles(year_from=2020, year_to=2021), ["Both"])
        self.assertEqual(self.client.get("/api/v1/records/facets/").json()["years"], [2024, 2022, 2020])

    def test_ordering_by_year_is_newest_first_with_unrecorded_last(self):
        self.assertEqual(self.titles(ordering="-year_accomplished"), ["Form", "Import", "Both", "Blank"])
        self.assertEqual(self.titles(ordering="year_accomplished"), ["Both", "Import", "Form", "Blank"])
