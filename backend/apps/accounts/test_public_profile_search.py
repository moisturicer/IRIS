"""Discover people search through its signed-in HTTP boundary (IR-697)."""

from django.urls import reverse
from rest_framework.test import APITestCase

from apps.accounts import profile
from apps.accounts.models import AdviserProfile, College, Course, Department, StudentProfile
from apps.accounts.tests import make_user
from apps.records.models import Record, RecordOwner, RecordType
from core.enums import PipelineStatus, RecordTypeName, RoleName


class PeopleSearchTests(APITestCase):
    PERSON_KEYS = {
        "id", "first_name", "middle_initial", "last_name", "role_label",
        "college_name", "department_name", "course_name", "photo_url",
        "published_paper_count",
    }

    def setUp(self):
        self.viewer = make_user("viewer@cit.edu", RoleName.STUDENT)
        self.ada = make_user("ada@cit.edu", RoleName.STUDENT)
        self.ada.first_name = "Ada"
        self.ada.last_name = "Lovelace"
        self.ada.save(update_fields=["first_name", "last_name"])
        profile.set_interests(self.ada, ["Analytical Engines"])
        self.college = College.objects.create(name="College of Engineering", code="COE-SEARCH")
        self.department = Department.objects.create(
            name="Computer Engineering", code="CPE-SEARCH", college=self.college,
        )
        self.course = Course.objects.create(name="Computer Engineering", department=self.department)
        StudentProfile.objects.create(user=self.ada, course=self.course)
        self.faculty = make_user("faculty@cit.edu", RoleName.ADVISER)
        AdviserProfile.objects.create(user=self.faculty, college=self.college, department=self.department)
        self.office = make_user("office@cit.edu", RoleName.ITSO)
        self.url = reverse("user-search")
        self.client.force_authenticate(self.viewer)

    def test_search_matches_names_and_interests_and_returns_only_public_fields(self):
        by_name = self.client.get(self.url, {"search": "Lovelace"})
        by_full_name = self.client.get(self.url, {"search": "Ada Lovelace"})
        by_interest = self.client.get(self.url, {"search": "analytical"})

        self.assertEqual([person["id"] for person in by_name.data["results"]], [self.ada.pk])
        self.assertEqual([person["id"] for person in by_full_name.data["results"]], [self.ada.pk])
        self.assertEqual([person["id"] for person in by_interest.data["results"]], [self.ada.pk])
        person = by_name.data["results"][0]
        self.assertEqual(set(person), self.PERSON_KEYS)
        self.assertEqual(person["role_label"], "Student")

    def test_college_department_and_role_filters_apply(self):
        for params, expected in (
            ({"college": self.college.pk}, {self.ada.pk, self.faculty.pk}),
            ({"department": self.department.pk}, {self.ada.pk, self.faculty.pk}),
            ({"role": "Faculty"}, {self.faculty.pk}),
            ({"role": "office"}, {self.office.pk}),
        ):
            with self.subTest(params=params):
                response = self.client.get(self.url, params)
                self.assertEqual(response.status_code, 200)
                self.assertEqual({row["id"] for row in response.data["results"]}, expected)

    def test_hidden_accounts_never_appear(self):
        hidden = [
            make_user("suspended@cit.edu", RoleName.STUDENT, is_locked=True),
            make_user("inactive@cit.edu", RoleName.STUDENT, is_active=False),
            make_user("unverified@cit.edu", RoleName.STUDENT, is_verified=False),
            make_user("deleted@cit.edu", RoleName.STUDENT, deleted_at=self.ada.date_joined),
            make_user("unapproved@cit.edu"),
        ]
        for person in hidden:
            person.first_name = "Hidden"
            person.save(update_fields=["first_name"])

        response = self.client.get(self.url, {"search": "Hidden"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["results"], [])

    def test_search_paginates_and_counts_only_published_owned_papers(self):
        second = make_user("second@cit.edu", RoleName.STUDENT)
        second.first_name = "Ada"
        second.last_name = "Second"
        second.save(update_fields=["first_name", "last_name"])
        thesis = RecordType.objects.get_or_create(name=RecordTypeName.THESIS_RESEARCH)[0]
        proposal = RecordType.objects.get_or_create(name=RecordTypeName.PROPOSAL)[0]
        published = Record.objects.create(
            title="Published", abstract="", record_type=thesis, added_by=self.ada,
            pipeline_status=PipelineStatus.PUBLISHED,
        )
        draft = Record.objects.create(
            title="Draft", abstract="", record_type=thesis, added_by=self.ada,
            pipeline_status=PipelineStatus.DRAFT,
        )
        proposal_record = Record.objects.create(
            title="Proposal", abstract="", record_type=proposal, added_by=self.ada,
            pipeline_status=PipelineStatus.PUBLISHED,
        )
        for record in (published, draft, proposal_record):
            RecordOwner.objects.create(record=record, user=self.ada, is_primary=True)

        first = self.client.get(self.url, {"search": "Ada", "page_size": 1})
        second_page = self.client.get(first.data["next"])

        self.assertEqual(first.status_code, 200)
        self.assertIsNotNone(first.data["next"])
        self.assertEqual(len(first.data["results"]), 1)
        self.assertEqual(second_page.status_code, 200)
        by_id = {
            person["id"]: person
            for person in first.data["results"] + second_page.data["results"]
        }
        self.assertEqual(by_id[self.ada.pk]["published_paper_count"], 1)
        self.assertEqual(by_id[second.pk]["published_paper_count"], 0)

    def test_people_search_requires_sign_in(self):
        self.client.force_authenticate(None)

        response = self.client.get(self.url, {"search": "Ada"})

        self.assertEqual(response.status_code, 401)
