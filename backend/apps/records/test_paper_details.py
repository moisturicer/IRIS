"""IR-686: sidebar facts and profile privacy at the record HTTP boundary."""
from datetime import timedelta

from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import AdviserProfile, Course, StudentProfile
from apps.records.models import RecordOwner
from apps.reviews.test_decisions import DecisionTestBase
from apps.reviews.workflow_test_helpers import make_user
from core.enums import Party, RoleName, SeatState


class PaperDetailsTests(DecisionTestBase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        for user, first, last in (
            (cls.owner, "Rhea", "Researcher"), (cls.adviser, "Ada", "Adviser"),
            (cls.itso, "Ian", "Reviewer"), (cls.itso2, "Ian", "Reviewer"),
            (cls.ierc, "Ina", "Reviewer"), (cls.rdco, "Rosa", "Coordinator"),
        ):
            user.first_name, user.last_name = first, last
            user.save(update_fields=["first_name", "last_name"])
        cls.course = Course.objects.select_related("department__college").get(name="BS Computer Science")
        StudentProfile.objects.update_or_create(user=cls.owner, defaults={"course": cls.course})
        StudentProfile.objects.update_or_create(user=cls.itso, defaults={"course": cls.course})
        AdviserProfile.objects.update_or_create(user=cls.adviser, defaults={
            "college": cls.course.department.college, "department": cls.course.department,
        })

    def details(self, record, viewer):
        return self.detail(record, viewer)["paper_details"]

    def test_rdco_reads_registration_affiliations_but_not_an_unrelated_review(self):
        record = self.routed(Party.ITSO)
        details = self.details(record, self.rdco)
        self.assertEqual(details["colleges"], ["College of Computer Studies"])
        self.assertEqual(details["programs"], ["BS Computer Science"])
        self.assertEqual(details["researchers"][0]["program"], self.course.name)
        self.assertEqual(details["researchers"][0]["email"], self.owner.email)
        self.assertIsNone(details["participants"])
        self.assertIsNone(details["due_dates"])

    def test_nonparticipant_sees_no_registration_affiliations_or_review_material(self):
        record = self.at_adviser()
        self.decided(record, self.adviser, "publish")
        details = self.details(record, self.reader)
        self.assertIsNone(details["colleges"])
        self.assertIsNone(details["programs"])
        self.assertIsNone(details["participants"])
        self.assertIsNone(details["due_dates"])
        owner = details["researchers"][0]
        self.assertEqual((owner["id"], owner["name"], owner["role"]),
                         (self.owner.pk, "Rhea Researcher", "Researcher"))
        self.assertEqual(owner["email"], self.owner.email)
        for key in ("college", "department", "program", "office"):
            self.assertIsNone(owner[key])
        adviser = details["adviser"]
        self.assertEqual(adviser["email"], self.adviser.email)
        self.assertEqual(adviser["college"], self.course.department.college.name)
        self.assertEqual(adviser["department"], self.course.department.name)
        self.assertIsNone(adviser["program"])

    def test_owner_reads_own_card_and_classification_but_no_coowners_program(self):
        record = self.routed(Party.ITSO)
        details = self.details(record, self.owner)
        self.assertEqual(details["programs"], [self.course.name])
        self.assertEqual(details["researchers"][0]["program"], self.course.name)
        coowner = make_user("coowner@cit.edu", RoleName.STUDENT)
        StudentProfile.objects.create(user=coowner, course=self.course)
        RecordOwner.objects.create(record=record, user=coowner)
        details = self.details(record, self.owner)
        self.assertIsNone(details["programs"])
        self.assertIsNone(details["colleges"])
        self.assertIsNone(details["researchers"][1]["program"])
        # A matching program must not let the client infer a coowner's data.
        self.assertEqual(self.details(record, self.rdco)["programs"], [self.course.name])

    def test_rdco_participant_gets_complete_cards_and_review_content(self):
        record = self.at_rdco()
        details = self.details(record, self.rdco)
        reviewer = next(p for p in details["participants"] if p["id"] == self.itso.pk)
        self.assertEqual(reviewer["email"], self.itso.email)
        self.assertEqual(reviewer["program"], self.course.name)
        self.assertEqual(reviewer["office"], "ITSO")
        self.assertIsNotNone(details["due_dates"])

    def test_participants_use_identity_not_names_and_cards_stay_minimal(self):
        record = self.routed(Party.ITSO)
        self.opened_seat(record, Party.ITSO, self.itso)
        self.opened_seat(record, Party.ITSO, self.itso2)
        details = self.details(record, self.adviser)
        self.assertEqual([p["id"] for p in details["researchers"]], [self.owner.pk])
        people = details["participants"]
        self.assertEqual([p["id"] for p in people],
                         [self.owner.pk, self.adviser.pk, self.itso.pk, self.itso2.pk])
        reviewers = [p for p in people if p["office"] == "ITSO"]
        self.assertEqual([p["name"] for p in reviewers], ["Ian Reviewer", "Ian Reviewer"])
        for person in reviewers:
            for key in ("email", "college", "department", "program"):
                self.assertIsNone(person[key])
        own = next(p for p in self.details(record, self.itso)["participants"] if p["id"] == self.itso.pk)
        self.assertEqual(own["email"], self.itso.email)
        self.client.force_authenticate(self.adviser)
        tracker = self.client.get(reverse("record-tracker", args=[record.pk]))
        self.assertEqual(tracker.status_code, 200)
        row = next(p for p in tracker.data["parties"] if p["party"] == Party.ITSO)
        self.assertEqual([s["reviewer"] for s in row["seats"]], [self.itso.pk, self.itso2.pk])

    def test_withdrawn_reviewer_is_omitted_but_completed_adviser_stays(self):
        record = self.routed(Party.ITSO)
        seat = self.opened_seat(record, Party.ITSO, self.itso)
        seat.state = SeatState.WITHDRAWN
        seat.save(update_fields=["state"])
        people = self.details(record, self.owner)["participants"]
        self.assertEqual([p["id"] for p in people], [self.owner.pk, self.adviser.pk])

    def test_flags_are_adr018_office_hints_and_deadlines_keep_paused_and_overdue(self):
        record = self.routed(Party.ITSO, Party.IERC)
        record.requested_itso = record.requested_ktto = True
        record.save(update_fields=["requested_itso", "requested_ktto"])
        past = timezone.now() - timedelta(days=1)
        itso = self.assignment(record, Party.ITSO)
        itso.due_at = itso.original_due_at = past
        itso.save(update_fields=["due_at", "original_due_at"])
        ierc = self.assignment(record, Party.IERC)
        ierc.due_at, ierc.document_pause_started_at = past, timezone.now()
        ierc.save(update_fields=["due_at", "document_pause_started_at"])
        details = self.details(record, self.owner)
        self.assertEqual([f["office"] for f in details["author_flags"]], [Party.ITSO, Party.KTTO])
        self.assertTrue(all(f["label"] and f["hint"] for f in details["author_flags"]))
        dues = {d["party"]: d for d in details["due_dates"]}
        self.assertTrue(dues[Party.ITSO]["is_overdue"])
        self.assertFalse(dues[Party.ITSO]["clock_paused"])
        self.assertEqual(dues[Party.ITSO]["original_due_at"], past.isoformat())
        self.assertTrue(dues[Party.IERC]["clock_paused"])
        self.assertFalse(dues[Party.IERC]["is_overdue"])
        self.assertEqual(dues[Party.IERC]["label"], "IERC")

    def test_missing_profiles_and_adviser_are_empty_without_invented_affiliations(self):
        record = self.make_record()
        record.adviser = None
        record.save(update_fields=["adviser"])
        StudentProfile.objects.filter(user=self.owner).delete()
        details = self.details(record, self.owner)
        self.assertEqual(details["colleges"], [])
        self.assertEqual(details["programs"], [])
        self.assertIsNone(details["adviser"])
        self.assertEqual(details["author_flags"], [])
        self.assertEqual(details["due_dates"], [])

    def test_inactive_adviser_is_not_given_picker_contact_fields(self):
        record = self.at_adviser()
        self.decided(record, self.adviser, "publish")
        self.adviser.is_active = False
        self.adviser.save(update_fields=["is_active"])
        adviser = self.details(record, self.reader)["adviser"]
        self.assertIsNone(adviser["email"])
        self.assertIsNone(adviser["college"])
        self.assertIsNone(adviser["department"])
