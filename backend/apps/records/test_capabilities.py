"""IR-418: action hints on the Record detail REST response (ADR-032 §10)."""

import shutil
import tempfile

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from django.urls import reverse
from rest_framework.test import APITestCase

from apps.records.models import Record, RecordOwner, RecordType
from apps.reviews import routing
from apps.reviews.models import RecordAssignment, ReviewerSeat
from apps.reviews.workflow_test_helpers import make_user
from core.enums import AssignmentState, Party, PipelineStatus, RecordTypeName, RoleName, SeatSource


class RecordCapabilitiesTests(APITestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # An attached file is written to disk; never into the checkout's media.
        cls._media_root = tempfile.mkdtemp(prefix="iris-test-media-")
        cls._media_override = override_settings(MEDIA_ROOT=cls._media_root)
        cls._media_override.enable()

    @classmethod
    def tearDownClass(cls):
        cls._media_override.disable()
        shutil.rmtree(cls._media_root, ignore_errors=True)
        super().tearDownClass()

    @classmethod
    def setUpTestData(cls):
        cls.owner = make_user("cap-owner@cit.edu", RoleName.STUDENT)
        cls.office = make_user("cap-itso@cit.edu", RoleName.ITSO)
        cls.adviser = make_user("cap-adviser@cit.edu", RoleName.ADVISER)
        cls.other_office = make_user("cap-ierc@cit.edu", RoleName.IERC)
        cls.record = Record.objects.create(
            title="Capabilities contract",
            abstract="A" * 40,
            record_type=RecordType.objects.get_or_create(name=RecordTypeName.THESIS_RESEARCH)[0],
            added_by=cls.owner,
            pipeline_status=PipelineStatus.DRAFT,
            adviser=cls.adviser,
        )
        RecordOwner.objects.create(record=cls.record, user=cls.owner, is_primary=True)

    def detail(self, user):
        self.client.force_authenticate(user)
        response = self.client.get(reverse("record-detail", args=[self.record.pk]))
        self.assertEqual(response.status_code, 200, response.data)
        return response.data

    def test_draft_and_published_capabilities_follow_the_viewers_authority(self):
        cases = [
            (PipelineStatus.DRAFT, self.owner, {"cite", "continue_draft", "edit_details"}),
            (PipelineStatus.DRAFT, self.office, {"cite"}),
            (PipelineStatus.PUBLISHED, self.owner, {"cite"}),
            (PipelineStatus.PUBLISHED, self.office, {"cite", "tag_ip"}),
        ]
        for state, viewer, expected in cases:
            with self.subTest(state=state, viewer=viewer.email):
                self.record.pipeline_status = state
                self.record.save(update_fields=["pipeline_status"])
                self.assertEqual(set(self.detail(viewer)["capabilities"]), expected)

        # `tags/` is the existing tag_ip authority: staff reach validation,
        # while a student owner is refused before the body is examined.
        url = reverse("record-tags", args=[self.record.pk])
        self.client.force_authenticate(self.office)
        self.assertEqual(self.client.patch(url, {"ip_type": "invalid"}, format="json").status_code, 400)
        self.client.force_authenticate(self.owner)
        self.assertEqual(self.client.patch(url, {"ip_type": "invalid"}, format="json").status_code, 403)

    def test_adviser_and_office_action_offers_follow_the_active_assignment(self):
        routing.enter_at_adviser(self.record, self.owner)
        cases = [
            (self.owner, {"cite"}, {"accept_route", "request_document", "attach_file"}),
            (self.adviser, {
                "cite", "open_review", "accept_route", "request_document",
                "request_revision", "accept_publish", "reject",
            }, {"attach_file", "tag_ip", "office_review"}),
            (self.office, {"cite"}, {"request_document", "attach_file", "accept_route"}),
        ]
        for viewer, present, absent in cases:
            with self.subTest(viewer=viewer.email, state="with adviser"):
                offered = set(self.detail(viewer)["capabilities"])
                self.assertTrue(present <= offered, offered)
                self.assertFalse(absent & offered, offered)

        # The upload endpoint is office staff only (`IsStaff`), so the Adviser,
        # who takes part, is refused there before the body is examined.
        upload = reverse("record-file-upload")
        self.client.force_authenticate(self.adviser)
        self.assertEqual(
            self.client.post(upload, {"record": self.record.pk}, format="multipart").status_code, 403,
        )

        # The route-options endpoint makes the same adviser/owner distinction
        # without changing the record.
        route_options = reverse("record-route-options", args=[self.record.pk])
        self.client.force_authenticate(self.adviser)
        self.assertEqual(self.client.get(route_options).status_code, 200)
        self.client.force_authenticate(self.owner)
        self.assertEqual(self.client.get(route_options).status_code, 403)

        self.client.force_authenticate(self.adviser)
        routed = self.client.post(
            reverse("record-accept-and-route", args=[self.record.pk]),
            {"to": [{"party": Party.ITSO}], "reason": "Assess the disclosure."},
            format="json",
        )
        self.assertEqual(routed.status_code, 200, routed.data)
        for viewer, present, absent in [
            (self.office, {"cite", "request_document", "attach_file"}, {"office_review"}),
            (self.other_office, {"cite"}, {"request_document", "attach_file"}),
        ]:
            with self.subTest(viewer=viewer.email, state="office pool"):
                offered = set(self.detail(viewer)["capabilities"])
                self.assertTrue(present <= offered, offered)
                self.assertFalse(absent & offered, offered)

        # The office now offered `attach_file` may file one; the office with no
        # part is refused, as its list says.
        def attach(user):
            self.client.force_authenticate(user)
            pdf = SimpleUploadedFile("note.pdf", b"%PDF-1.4\n%%EOF\n", content_type="application/pdf")
            return self.client.post(upload, {"record": self.record.pk, "file": pdf}, format="multipart")

        self.assertEqual(attach(self.office).status_code, 201)
        self.assertEqual(attach(self.other_office).status_code, 403)

        assignment = RecordAssignment.objects.get(
            record=self.record, party=Party.ITSO, state=AssignmentState.ACTIVE,
        )
        seat = ReviewerSeat.objects.create(
            assignment=assignment, reviewer=self.office, source=SeatSource.CLAIMED,
        )
        self.client.force_authenticate(self.office)
        opened = self.client.post(reverse("seat-open", args=[seat.pk]))
        self.assertEqual(opened.status_code, 200, opened.data)
        offered = set(self.detail(self.office)["capabilities"])
        self.assertTrue({
            "open_review", "office_review", "add_reviewer", "route",
            "request_revision", "request_document", "attach_file",
        } <= offered, offered)

        # A pool member has no office-review authority until holding a seat;
        # this one does, and reaches body validation on the same endpoint.
        office_review = reverse("record-office-review", args=[self.record.pk])
        self.client.force_authenticate(self.other_office)
        self.assertEqual(self.client.post(office_review, {}, format="json").status_code, 403)
        self.client.force_authenticate(self.office)
        self.assertEqual(self.client.post(office_review, {}, format="json").status_code, 400)
