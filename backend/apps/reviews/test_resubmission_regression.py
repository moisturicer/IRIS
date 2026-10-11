"""
IR-233: clearance-aware resubmission, pinned at the API so it survives IR-255.

**Why this module stands alone.** It tests the clearance-aware revision path
independently of the retired fixed-pipeline characterisation suite.

**What reproducing the report found (2026-09-15).** The Record in the report is
seed_demo's `[DEMO] Declined by IERC, ITSO and KTTO preserved`. The backend log
shows the owner's first resubmission refused with a 400. Its 77-byte body is
exactly the upload guard's `{"detail":"Please upload at least one updated
document before resubmitting."}`. The Record never left `declined`. The paper
view kept showing the IERC decline in both the clearance track and the review
history, and showed the refusal as a small red line under the button. After an
upload, the next resubmission succeeded: IERC reset to pending, and ITSO and
KTTO stayed cleared and preserved. **So the clearance-aware transition works.
The upload guard refused a resubmission that had no revision, and the paper
view made the refusal look like a second decline.**

That is why this module has three tests, not one:

- **No revision.** The resubmission is refused and the Record still awaits
  resubmission. That is the reported click path under ADR-021 §11.
- **After an upload.** Only the requesting office's clearance resets.
- **After a metadata-only revision.** The same clearance-aware behavior now
  passes through the new-version endpoint (IR-260).

What no test here covers is the display half: that the paper view shows a
refusal as a refusal. That is IR-259's Action required panel.

The assertions describe behavior and name no pipeline stage.
"""

import shutil
import tempfile
from unittest import mock

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from rest_framework.test import APITestCase

from apps.accounts.models import Role, User
from apps.documents.models import UploadSlot
from apps.records.models import Record, RecordOwner, RecordType
from core.enums import PipelineStatus, RecordTypeName, RoleName

DOCUMENT_SUBMIT = "/api/v1/documents/submit/"

#: The office that asks for changes in the reported case, and its two peers.
REQUESTING_OFFICE = "ierc"
PEER_OFFICES = ("itso", "ktto")


class SetupFailed(Exception):
    """
    A step outside the behaviour under test did not produce the state the test needs.

    Deliberately not an `AssertionError`. The expected-failure marker below is
    limited to `AssertionError`, so a broken setup errors the test instead of
    being counted as the known defect.
    """


def _require_status(response, status_code, step):
    if response.status_code != status_code:
        raise SetupFailed(
            f"{step}: expected HTTP {status_code}, got {response.status_code} "
            f"{getattr(response, 'data', response.content)!r}"
        )
    return response


class ResubmissionRegressionTests(APITestCase):
    """The reported sequence: three offices requested, two clear, IERC asks for changes."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # The upload test writes a real file. Keep it out of the checkout's media/.
        cls._media_root = tempfile.mkdtemp(prefix="iris-ir233-media-")
        cls._media_override = override_settings(MEDIA_ROOT=cls._media_root)
        cls._media_override.enable()

    @classmethod
    def tearDownClass(cls):
        cls._media_override.disable()
        shutil.rmtree(cls._media_root, ignore_errors=True)
        super().tearDownClass()

    @classmethod
    def setUpTestData(cls):
        def user(email, role_name):
            # Roles are seeded by migration with explicit keys, so create() would
            # collide with the sequence (IR-126).
            role = Role.objects.get_or_create(name=role_name)[0]
            return User.objects.create_user(
                email=email, password="TestPass123!", first_name="Test",
                last_name="User", role=role, is_verified=True,
            )

        cls.owner = user("ir233-owner@cit.edu", RoleName.STUDENT)
        cls.rdco = user("ir233-rdco@cit.edu", RoleName.RDCO)
        cls.adviser = user("ir233-adviser@cit.edu", RoleName.ADVISER)
        cls.itso = user("ir233-itso@cit.edu", RoleName.ITSO)
        cls.ierc = user("ir233-ierc@cit.edu", RoleName.IERC)
        cls.ktto = user("ir233-ktto@cit.edu", RoleName.KTTO)

    # -- setup: may change at the IR-260 cutover ---------------------------

    def _project_where_one_office_asked_for_changes(self):
        """
        The reported Record: a Project that requested ITSO, IERC and KTTO.
        ITSO and KTTO have cleared, and IERC has asked for changes.
        """
        record_type = RecordType.objects.filter(name=RecordTypeName.PROJECT).first()
        if record_type is None:
            raise SetupFailed("RecordType 'Project' is not seeded; migrations incomplete")
        from apps.reviews import seats
        from apps.reviews.models import RecordAssignment
        from apps.reviews.office_review import CLEARED, record_office_review
        from apps.reviews.revisions import request_revision
        from apps.reviews.routing import accept_and_route, enter_at_adviser

        record = Record.objects.create(
            title="IR-233 regression",
            abstract="A" * 40,
            record_type=record_type,
            added_by=self.owner,
            pipeline_status=PipelineStatus.DRAFT,
            adviser=self.adviser,
            requested_itso=True,
            requested_ierc=True,
            requested_ktto=True,
        )
        RecordOwner.objects.create(record=record, user=self.owner, is_primary=True)

        entry = enter_at_adviser(record, self.owner)
        seats.open_review(entry.seats.get(), self.adviser)
        accept_and_route(
            record, self.adviser,
            to=[{"party": party, "nominee": reviewer.pk} for party, reviewer in (
                ("itso", self.itso), ("ierc", self.ierc), ("ktto", self.ktto),
            )],
            reason="Specialist review is needed.",
        )
        for party, reviewer, comment in (
            ("itso", self.itso, "Prior-art search complete."),
            ("ktto", self.ktto, "Commercialisation potential noted."),
        ):
            assignment = RecordAssignment.objects.get(record=record, party=party, state="active")
            seats.open_review(assignment.seats.get(reviewer=reviewer), reviewer)
            record_office_review(record, reviewer, outcome=CLEARED, comment=comment)
        ierc = RecordAssignment.objects.get(record=record, party="ierc", state="active")
        seats.open_review(ierc.seats.get(reviewer=self.ierc), self.ierc)
        request_revision(record, self.ierc, reason="Consent form for human participants is missing.")

        if not self._awaits_resubmission(self._detail(record)):
            raise SetupFailed(
                "the office's request for changes did not leave the Record awaiting resubmission"
            )
        return record

    def _revise_by_uploading_a_document(self, record):
        slot = UploadSlot.objects.create(
            name="Ethics consent form", record_type=record.record_type
        )
        self.client.force_authenticate(self.owner)
        # Extraction is queued work, and this test is about the workflow.
        with mock.patch("apps.documents.tasks.extract_pdf_text.delay"):
            _require_status(
                self.client.post(
                    DOCUMENT_SUBMIT,
                    {
                        "record": record.pk,
                        "slot": slot.pk,
                        "file": SimpleUploadedFile(
                            "consent.pdf", b"%PDF-1.4 consent", content_type="application/pdf"
                        ),
                    },
                    format="multipart",
                ),
                201,
                "owner uploads the requested document",
            )

    def _revise_metadata_only(self, record):
        self.client.force_authenticate(self.owner)
        _require_status(
            self.client.patch(
                f"/api/v1/records/{record.pk}/",
                {"abstract": "Revised to describe how participant consent is obtained. " * 2},
                format="json",
            ),
            200,
            "owner edits the record's metadata",
        )

    # -- observation: must not change at the cutover -----------------------

    def _resubmit(self, record):
        self.client.force_authenticate(self.owner)
        return self.client.post(f"/api/v1/records/{record.pk}/new-version/", {}, format="json")

    def _detail(self, record):
        self.client.force_authenticate(self.owner)
        return _require_status(
            self.client.get(f"/api/v1/records/{record.pk}/"), 200, "owner reads the record"
        ).json()

    def _clearances(self, detail):
        return {c["office"]: c for c in detail["clearances"]}

    def _awaits_resubmission(self, detail):
        """
        Whether the owner still has to resubmit, read from the record detail.

        Today only `pipeline_status == "declined"` means that. Under ADR-021 §4,
        IR-258 adds a computed `workflow_state` to the detail payload
        (`docs/workflow_routing_architecture.md` §4.1, §8.2), whose
        `awaiting_resubmission` value means it, and IR-260 stops storing
        `declined`. Reading whichever the API provides keeps every assertion
        unchanged across the cutover.

        **The fallback refuses to answer rather than guess.** If `declined` is no
        longer a pipeline status but `workflow_state` is missing, the field was
        named differently. A plain `== "declined"` would then report "not
        awaiting" for every Record, and the assertions would pass vacuously.
        """
        if "workflow_state" in detail:
            return detail["workflow_state"] == "awaiting_resubmission"
        if "declined" not in {s.value for s in PipelineStatus}:
            raise SetupFailed(
                "`declined` is no longer a pipeline status and the detail payload has no "
                "`workflow_state`; point this helper at whatever now says a Record awaits "
                "resubmission"
            )
        return detail["pipeline_status"] == "declined"

    # -- the behaviour: must not change at the cutover ---------------------

    def _assert_clearance_aware_resubmission(self, record, response):
        self.assertEqual(
            response.status_code, 200,
            f"the resubmission was refused: {getattr(response, 'data', response.content)!r}",
        )

        detail = self._detail(record)
        self.assertFalse(
            self._awaits_resubmission(detail),
            "the Record still awaits resubmission after a successful resubmit",
        )

        clearances = self._clearances(detail)
        self.assertEqual(
            clearances[REQUESTING_OFFICE]["status"], "pending",
            "the office that asked for changes must review the revision",
        )
        # A plain loop, not subTest: pytest reports subtests separately from the
        # xfail marker, which would blur what "expected failure" covers.
        for office in PEER_OFFICES:
            self.assertEqual(
                clearances[office]["status"], "cleared",
                f"{office} had cleared and did not ask for changes, so it keeps its clearance",
            )
            self.assertTrue(
                clearances[office]["preserved"],
                f"{office}'s clearance must be marked as carried over, not granted again",
            )

    def test_resubmission_with_no_revision_is_refused_and_still_awaits_resubmission(self):
        """The reported click path. Correct today and under ADR-021 §11."""
        record = self._project_where_one_office_asked_for_changes()
        before = self._clearances(self._detail(record))

        response = self._resubmit(record)

        self.assertEqual(
            response.status_code, 400,
            "a resubmission with nothing revised must be refused, not accepted",
        )
        self.assertTrue(
            response.data.get("detail"),
            "the refusal must say why, so the owner is not left guessing",
        )
        detail = self._detail(record)
        self.assertTrue(
            self._awaits_resubmission(detail),
            "a refused resubmission must leave the Record awaiting resubmission",
        )
        self.assertEqual(
            {office: c["status"] for office, c in self._clearances(detail).items()},
            {office: c["status"] for office, c in before.items()},
            "a refused resubmission must not touch any clearance",
        )

    def test_resubmission_after_an_upload_resets_only_the_requesting_office(self):
        """The part of the report that already works. It must keep working through IR-260."""
        record = self._project_where_one_office_asked_for_changes()
        self._revise_by_uploading_a_document(record)

        response = self._resubmit(record)

        self._assert_clearance_aware_resubmission(record, response)

    def test_resubmission_after_a_metadata_revision_resets_only_the_requesting_office(self):
        record = self._project_where_one_office_asked_for_changes()
        self._revise_metadata_only(record)

        response = self._resubmit(record)

        self._assert_clearance_aware_resubmission(record, response)
