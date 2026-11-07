"""
A person's public profile, through the REST boundary (IR-696, spec IR-694).

The contract these hold to is the one agreed for IR-696 and recorded in
`docs/testing/traceability/IR-696.md`: `GET /users/<id>/profile/` and its
`research/`, `advised/` and `collaborators/` lists, plus `adviser_has_profile`
and `owners[].has_profile` on a record's detail. Every test drives the
HTTP boundary; none reaches into `apps.accounts.public_profile`.

A person the server hides answers one 404, identical to a missing id, for every
route, so the API never confirms a hidden account exists.
"""
import json
import shutil
import tempfile

from django.test import override_settings
from django.urls import reverse
from rest_framework.test import APITestCase

from apps.accounts import profile
from apps.accounts.models import AdviserProfile, College, Course, Department, StudentProfile
from apps.accounts.tests import make_user
from apps.records.models import Author, Classification, Record, RecordOwner, RecordType
from core.enums import PipelineStatus, RecordTypeName, RoleName

PROFILE_KEYS = {
    "id", "first_name", "middle_initial", "last_name", "role_label", "college_name",
    "department_name", "course_name", "bio", "research_interests", "photo_url",
}
PAPER_KEYS = {
    "id", "title", "authors", "classification_name", "record_type_name", "publication_year", "views",
}
COLLABORATOR_KEYS = {"id", "first_name", "middle_initial", "last_name", "photo_url", "shared_papers"}
LISTS = ("research", "advised", "collaborators")
MISSING_ID = 2_000_000_000


def make_person(email, role_name=None, *, first_name="Test", last_name="User", **extra):
    """`make_user` with a name: it fixes the names itself, so they cannot ride in `extra`."""
    user = make_user(email, role_name, **extra)
    user.first_name, user.last_name = first_name, last_name
    user.save(update_fields=["first_name", "last_name"])
    return user


def profile_url(user_id, section=None):
    name = "user-profile" if section is None else f"user-profile-{section}"
    return reverse(name, kwargs={"pk": user_id})


class PublicProfileTestCase(APITestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        root = tempfile.mkdtemp(prefix="iris-public-profile-media-")
        cls.addClassCleanup(shutil.rmtree, root, ignore_errors=True)
        override = override_settings(MEDIA_ROOT=root)
        override.enable()
        cls.addClassCleanup(override.disable)

    def setUp(self):
        self.viewer = make_person("viewer@cit.edu", RoleName.STUDENT)
        self.ana = make_person("ana@cit.edu", RoleName.STUDENT, first_name="Ana", last_name="Reyes")
        self.maria = make_person("maria@cit.edu", RoleName.ADVISER, first_name="Maria", last_name="Santos")
        self.thesis = RecordType.objects.get_or_create(name=RecordTypeName.THESIS_RESEARCH)[0]
        self.client.force_authenticate(self.viewer)

    def paper(self, title, owners=(), adviser=None, *, status=PipelineStatus.PUBLISHED,
              record_type=None, **extra):
        record = Record.objects.create(
            title=title, abstract="An abstract.", record_type=record_type or self.thesis,
            added_by=owners[0] if owners else self.ana, adviser=adviser,
            pipeline_status=status, **extra,
        )
        for index, owner in enumerate(owners):
            RecordOwner.objects.create(record=record, user=owner, is_primary=index == 0)
        return record

    def get(self, user_id, section=None, **query):
        return self.client.get(profile_url(user_id, section), query)

    def ids(self, response):
        return [row["id"] for row in response.data["results"]]


class ProfilePayloadTests(PublicProfileTestCase):
    def test_a_student_profile_carries_the_contract_fields_and_nothing_else(self):
        college = College.objects.create(name="College of Engineering", code="COE-T")
        department = Department.objects.create(name="Computer Engineering", code="CPE-T", college=college)
        course = Course.objects.create(name="BS Computer Engineering", department=department)
        StudentProfile.objects.create(user=self.ana, course=course)
        self.ana.middle_initial = "M."
        self.ana.bio = "I build robots."
        self.ana.save(update_fields=["middle_initial", "bio"])
        profile.set_interests(self.ana, ["Robotics", "Embedded systems"])

        response = self.get(self.ana.pk)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(set(response.data), PROFILE_KEYS)
        self.assertEqual(response.data["id"], self.ana.pk)
        self.assertEqual(response.data["first_name"], "Ana")
        self.assertEqual(response.data["middle_initial"], "M.")
        self.assertEqual(response.data["last_name"], "Reyes")
        self.assertEqual(response.data["role_label"], "Student")
        self.assertEqual(response.data["college_name"], "College of Engineering")
        self.assertEqual(response.data["department_name"], "Computer Engineering")
        self.assertEqual(response.data["course_name"], "BS Computer Engineering")
        self.assertEqual(response.data["bio"], "I build robots.")
        self.assertEqual(response.data["research_interests"], ["Robotics", "Embedded systems"])

    def test_an_adviser_carries_their_college_and_department_and_no_course(self):
        college = College.objects.create(name="College of Computer Studies", code="CCS-T")
        department = Department.objects.create(name="Information Technology", code="IT-T", college=college)
        AdviserProfile.objects.create(user=self.maria, college=college, department=department)

        data = self.get(self.maria.pk).data

        self.assertEqual(data["role_label"], "Adviser")
        self.assertEqual(data["college_name"], "College of Computer Studies")
        self.assertEqual(data["department_name"], "Information Technology")
        self.assertEqual(data["course_name"], "")

    def test_each_office_is_its_own_label_and_is_never_called_faculty(self):
        for role in (RoleName.ITSO, RoleName.IERC, RoleName.KTTO, RoleName.RDCO):
            with self.subTest(role=role):
                staff = make_person(f"{role.lower()}@cit.edu", role)
                self.assertEqual(self.get(staff.pk).data["role_label"], role.value)

    def test_a_person_with_nothing_set_reads_with_empty_values(self):
        data = self.get(self.ana.pk).data

        self.assertEqual(data["middle_initial"], "")
        self.assertEqual(data["college_name"], "")
        self.assertEqual(data["department_name"], "")
        self.assertEqual(data["course_name"], "")
        self.assertEqual(data["bio"], "")
        self.assertEqual(data["research_interests"], [])
        self.assertIsNone(data["photo_url"])

    def test_the_photo_is_the_existing_authenticated_path_with_its_version(self):
        self.ana.photo.name = "profile_photos/x.jpg"
        self.ana.photo_version = 3
        self.ana.save(update_fields=["photo", "photo_version"])

        self.assertEqual(self.get(self.ana.pk).data["photo_url"], f"/users/{self.ana.pk}/photo/?v=3")

    def test_no_security_detail_or_contact_ever_appears_in_any_response(self):
        coordinator = make_person("coord@cit.edu", RoleName.ITSO, is_office_coordinator=True)
        self.paper("Shared", [coordinator, self.ana], self.maria)
        banned = ("email", "cit.edu", "coordinator", "locked", "is_active", "is_verified",
                  "password", "credential", "date_joined", "consent")

        for user in (coordinator, self.ana, self.maria):
            for section in (None, *LISTS):
                with self.subTest(user=user.email, section=section):
                    body = json.dumps(self.get(user.pk, section).data).lower()
                    for word in banned:
                        self.assertNotIn(word, body)

    def test_a_person_reads_their_own_profile_the_same_way(self):
        self.client.force_authenticate(self.ana)

        self.assertEqual(self.get(self.ana.pk).status_code, 200)

    def test_signed_out_callers_are_refused_on_every_route(self):
        self.client.force_authenticate(None)

        for section in (None, *LISTS):
            with self.subTest(section=section):
                self.assertEqual(self.get(self.ana.pk, section).status_code, 401)


class HiddenAccountTests(PublicProfileTestCase):
    """Suspended, inactive, unapproved, System Admin and missing: one 404, one body."""

    def hidden_accounts(self):
        return {
            "suspended": make_person("suspended@cit.edu", RoleName.STUDENT, is_locked=True),
            "inactive": make_person("inactive@cit.edu", RoleName.STUDENT, is_active=False),
            "unverified": make_person("unverified@cit.edu", RoleName.STUDENT, is_verified=False),
            "unapproved": make_person("unapproved@cit.edu", None),
            "system admin": make_person("sysadmin@cit.edu", RoleName.SYSTEM_ADMIN),
        }

    def test_every_hidden_account_answers_the_missing_ids_404_on_every_route(self):
        hidden = self.hidden_accounts()
        for section in (None, *LISTS):
            missing = self.get(MISSING_ID, section)
            self.assertEqual(missing.status_code, 404)
            for label, user in hidden.items():
                with self.subTest(account=label, section=section):
                    response = self.get(user.pk, section)
                    self.assertEqual(response.status_code, 404)
                    self.assertEqual(response.content, missing.content)

    def test_a_hidden_account_stays_hidden_from_their_own_session_and_from_offices(self):
        suspended = self.hidden_accounts()["suspended"]
        rdco = make_person("rdco@cit.edu", RoleName.RDCO)

        for caller in (suspended, rdco):
            self.client.force_authenticate(caller)
            self.assertEqual(self.get(suspended.pk).status_code, 404)


class PaperListTests(PublicProfileTestCase):
    def test_research_holds_the_published_papers_the_person_owns(self):
        mine = self.paper("Mine", [self.ana], self.maria)
        self.paper("Someone else's", [self.viewer], self.maria)

        self.assertEqual(self.ids(self.get(self.ana.pk, "research")), [mine.pk])

    def test_advised_holds_the_published_papers_the_person_was_adviser_on(self):
        advised = self.paper("Advised", [self.ana], self.maria)
        owned = self.paper("Owned by the adviser", [self.maria])

        self.assertEqual(self.ids(self.get(self.maria.pk, "advised")), [advised.pk])
        self.assertEqual(self.ids(self.get(self.maria.pk, "research")), [owned.pk])

    def test_papers_follow_discover_visibility_and_nothing_else_appears(self):
        shown = self.paper("Published", [self.ana], self.maria)
        for status in (PipelineStatus.DRAFT, PipelineStatus.IN_REVIEW, PipelineStatus.COMPLETED,
                       PipelineStatus.REJECTED, PipelineStatus.APPROVED, PipelineStatus.PENDING_DELETE):
            self.paper(f"Not listed: {status}", [self.ana], self.maria, status=status)
        self.paper("Deleted", [self.ana], self.maria, is_deleted=True)
        proposal_type = RecordType.objects.get_or_create(name=RecordTypeName.PROPOSAL)[0]
        self.paper("A Proposal", [self.ana], self.maria, record_type=proposal_type)

        self.assertEqual(self.ids(self.get(self.ana.pk, "research")), [shown.pk])
        self.assertEqual(self.ids(self.get(self.maria.pk, "advised")), [shown.pk])

    def test_a_person_does_not_see_their_own_drafts_on_their_profile(self):
        self.paper("My draft", [self.ana], status=PipelineStatus.DRAFT)
        self.client.force_authenticate(self.ana)

        self.assertEqual(self.get(self.ana.pk, "research").data["results"], [])

    def test_a_paper_carries_its_fields_and_its_view_count_and_no_totals(self):
        classification = Classification.objects.create(name="Engineering")
        record = self.paper(
            "Mine", [self.ana], self.maria, classification=classification,
            publication_year=2025, access_count=41,
        )
        Author.objects.create(record=record, name="Ana M. Reyes")
        Author.objects.create(record=record, name="Jomar Ybanez")

        response = self.get(self.ana.pk, "research")

        self.assertEqual(set(response.data), {"next", "results"})
        row = response.data["results"][0]
        self.assertEqual(set(row), PAPER_KEYS)
        self.assertEqual(row["id"], record.pk)
        self.assertEqual(row["title"], "Mine")
        self.assertCountEqual(row["authors"], ["Ana M. Reyes", "Jomar Ybanez"])
        self.assertEqual(row["classification_name"], "Engineering")
        self.assertEqual(row["record_type_name"], "Thesis / Research")
        self.assertEqual(row["publication_year"], 2025)
        self.assertEqual(row["views"], 41)
        body = json.dumps(response.data).lower()
        for word in ("count", "total", "citation"):
            self.assertNotIn(word, body)

    def test_a_paper_without_an_area_or_year_reads_empty_not_missing(self):
        self.paper("Bare", [self.ana])

        row = self.get(self.ana.pk, "research").data["results"][0]

        self.assertEqual(row["classification_name"], "")
        self.assertIsNone(row["publication_year"])
        self.assertEqual(row["authors"], [])

    def test_newest_first_and_paging_ends_with_a_null_next_and_no_count(self):
        papers = [self.paper(f"Paper {n}", [self.ana]) for n in range(5)]
        newest_first = [p.pk for p in reversed(papers)]

        first = self.get(self.ana.pk, "research", page=1, page_size=2)
        second = self.get(self.ana.pk, "research", page=2, page_size=2)
        last = self.get(self.ana.pk, "research", page=3, page_size=2)

        self.assertEqual(self.ids(first), newest_first[:2])
        self.assertEqual(self.ids(second), newest_first[2:4])
        self.assertEqual(self.ids(last), newest_first[4:])
        self.assertIsNotNone(first.data["next"])
        self.assertIsNotNone(second.data["next"])
        self.assertIsNone(last.data["next"])
        for response in (first, second, last):
            self.assertNotIn("count", response.data)

    def test_the_next_link_leads_to_the_next_page(self):
        for n in range(3):
            self.paper(f"Paper {n}", [self.ana])

        first = self.get(self.ana.pk, "research", page_size=2)
        followed = self.client.get(first.data["next"])

        self.assertEqual(followed.status_code, 200)
        self.assertEqual(len(followed.data["results"]), 1)
        self.assertIsNone(followed.data["next"])

    def test_a_page_past_the_end_is_empty_not_an_error(self):
        self.paper("Only", [self.ana])

        response = self.get(self.ana.pk, "research", page=9, page_size=10)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data, {"next": None, "results": []})

    def test_a_bad_page_or_size_is_refused(self):
        for query in ({"page": "0"}, {"page": "x"}, {"page_size": "0"}, {"page_size": "-1"}, {"page_size": "x"}):
            with self.subTest(query=query):
                self.assertEqual(self.get(self.ana.pk, "research", **query).status_code, 400)

    def test_an_oversized_page_size_is_capped_not_honoured(self):
        for n in range(60):
            self.paper(f"Paper {n}", [self.ana])

        response = self.get(self.ana.pk, "research", page_size=10_000)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data["results"]), 50)
        self.assertIsNotNone(response.data["next"])


class CollaboratorTests(PublicProfileTestCase):
    def setUp(self):
        super().setUp()
        self.ben = make_person("ben@cit.edu", RoleName.STUDENT, first_name="Ben", last_name="Cruz")
        self.cara = make_person("cara@cit.edu", RoleName.STUDENT, first_name="Cara", last_name="Abad")

    def collaborators(self, user):
        return {row["id"]: row["shared_papers"] for row in self.get(user.pk, "collaborators").data["results"]}

    def test_co_owners_and_the_adviser_are_collaborators_of_an_owner(self):
        self.paper("Shared", [self.ana, self.ben], self.maria)

        self.assertEqual(self.collaborators(self.ana), {self.ben.pk: 1, self.maria.pk: 1})

    def test_advisees_and_co_owners_are_collaborators_of_the_adviser(self):
        self.paper("Shared", [self.ana, self.ben], self.maria)

        self.assertEqual(self.collaborators(self.maria), {self.ana.pk: 1, self.ben.pk: 1})

    def test_each_collaborator_carries_the_number_of_papers_shared(self):
        self.paper("One", [self.ana, self.ben], self.maria)
        self.paper("Two", [self.ana, self.ben])
        self.paper("Three", [self.ana], self.maria)

        self.assertEqual(self.collaborators(self.ana), {self.ben.pk: 2, self.maria.pk: 2})

    def test_the_person_is_never_their_own_collaborator(self):
        self.paper("Shared", [self.ana, self.ben])

        self.assertNotIn(self.ana.pk, self.collaborators(self.ana))

    def test_only_published_papers_count(self):
        for status in (PipelineStatus.DRAFT, PipelineStatus.IN_REVIEW, PipelineStatus.COMPLETED,
                       PipelineStatus.REJECTED):
            self.paper(f"Not listed: {status}", [self.ana, self.ben], self.maria, status=status)
        self.paper("Deleted", [self.ana, self.ben], self.maria, is_deleted=True)
        proposal_type = RecordType.objects.get_or_create(name=RecordTypeName.PROPOSAL)[0]
        self.paper("A Proposal", [self.ana, self.ben], self.maria, record_type=proposal_type)

        self.assertEqual(self.collaborators(self.ana), {})

    def test_byline_authors_without_an_account_are_left_out(self):
        record = self.paper("Mine", [self.ana])
        Author.objects.create(record=record, name="Ben Cruz")  # a name that matches an account
        Author.objects.create(record=record, name="Nobody Atall")

        self.assertEqual(self.collaborators(self.ana), {})

    def test_accounts_the_server_hides_are_left_out(self):
        hidden = {
            "suspended": make_person("s@cit.edu", RoleName.STUDENT, is_locked=True),
            "inactive": make_person("i@cit.edu", RoleName.STUDENT, is_active=False),
            "unapproved": make_person("u@cit.edu", None),
            "system admin": make_person("sa@cit.edu", RoleName.SYSTEM_ADMIN),
        }
        self.paper("Shared", [self.ana, *hidden.values(), self.ben])

        self.assertEqual(self.collaborators(self.ana), {self.ben.pk: 1})

    def test_most_papers_shared_first_then_name(self):
        self.paper("A", [self.ana, self.ben])
        self.paper("B", [self.ana, self.ben])
        self.paper("C", [self.ana, self.cara])
        self.paper("D", [self.ana, self.maria])

        order = [row["id"] for row in self.get(self.ana.pk, "collaborators").data["results"]]

        # Ben shares two; Cara (Abad) and Maria (Santos) share one each, by last name.
        self.assertEqual(order, [self.ben.pk, self.cara.pk, self.maria.pk])

    def test_a_collaborator_row_carries_only_the_contract_fields(self):
        self.ben.middle_initial = "Q."
        self.ben.photo.name = "profile_photos/b.jpg"
        self.ben.photo_version = 2
        self.ben.save(update_fields=["middle_initial", "photo", "photo_version"])
        self.paper("Shared", [self.ana, self.ben])

        row = self.get(self.ana.pk, "collaborators").data["results"][0]

        self.assertEqual(set(row), COLLABORATOR_KEYS)
        self.assertEqual(row["id"], self.ben.pk)
        self.assertEqual((row["first_name"], row["middle_initial"], row["last_name"]), ("Ben", "Q.", "Cruz"))
        self.assertEqual(row["photo_url"], f"/users/{self.ben.pk}/photo/?v=2")
        self.assertEqual(row["shared_papers"], 1)

    def test_collaborators_page_like_the_other_lists(self):
        people = [make_person(f"p{n}@cit.edu", RoleName.STUDENT, first_name="P", last_name=f"Name{n:02d}")
                  for n in range(5)]
        for person in people:
            self.paper(f"With {person.last_name}", [self.ana, person])

        first = self.get(self.ana.pk, "collaborators", page=1, page_size=2)
        last = self.get(self.ana.pk, "collaborators", page=3, page_size=2)

        self.assertEqual(len(first.data["results"]), 2)
        self.assertIsNotNone(first.data["next"])
        self.assertEqual(len(last.data["results"]), 1)
        self.assertIsNone(last.data["next"])
        self.assertNotIn("count", first.data)


class RecordDetailFlagTests(PublicProfileTestCase):
    """`adviser_has_profile` and `owners[].has_profile`: link only to a page that opens."""

    def detail(self, record):
        response = self.client.get(reverse("record-detail", kwargs={"pk": record.pk}))
        self.assertEqual(response.status_code, 200)
        return response.data

    def test_a_published_paper_flags_its_adviser_and_owners_who_have_a_profile(self):
        record = self.paper("Published", [self.ana], self.maria)

        data = self.detail(record)

        self.assertIs(data["adviser_has_profile"], True)
        self.assertEqual([owner["has_profile"] for owner in data["owners"]], [True])

    def test_a_person_the_server_hides_is_not_flagged(self):
        locked = make_person("locked@cit.edu", RoleName.ADVISER, is_locked=True)
        gone = make_person("gone@cit.edu", RoleName.STUDENT, is_active=False)
        record = self.paper("Published", [self.ana, gone], locked)

        data = self.detail(record)

        self.assertIs(data["adviser_has_profile"], False)
        by_user = {owner["user"]: owner["has_profile"] for owner in data["owners"]}
        self.assertEqual(by_user, {self.ana.pk: True, gone.pk: False})

    def test_a_paper_that_is_not_published_flags_no_one(self):
        record = self.paper("In review", [self.ana], self.maria, status=PipelineStatus.IN_REVIEW)
        self.client.force_authenticate(self.ana)

        data = self.detail(record)

        self.assertIs(data["adviser_has_profile"], False)
        self.assertEqual([owner["has_profile"] for owner in data["owners"]], [False])

    def test_a_published_proposal_flags_no_one(self):
        proposal_type = RecordType.objects.get_or_create(name=RecordTypeName.PROPOSAL)[0]
        record = self.paper("A Proposal", [self.ana], self.maria, record_type=proposal_type)

        data = self.detail(record)

        self.assertIs(data["adviser_has_profile"], False)
        self.assertEqual([owner["has_profile"] for owner in data["owners"]], [False])

    def test_a_paper_with_no_adviser_flags_none(self):
        record = self.paper("Published", [self.ana])

        self.assertIs(self.detail(record)["adviser_has_profile"], False)

    def test_each_flag_agrees_with_whether_the_profile_opens(self):
        locked = make_person("locked@cit.edu", RoleName.STUDENT, is_locked=True)
        record = self.paper("Published", [self.ana, locked], self.maria)

        data = self.detail(record)

        for owner in data["owners"]:
            self.assertEqual(owner["has_profile"], self.get(owner["user"]).status_code == 200)
        self.assertEqual(data["adviser_has_profile"], self.get(self.maria.pk).status_code == 200)
