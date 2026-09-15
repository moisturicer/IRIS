"""
IR-233: clearance-aware resubmission, pinned at the API so it survives IR-255.

**Why this module stands alone.** IR-260 retires `test_workflow_characterisation.py`
and the suites built on it, because they describe the fixed pipeline that
ADR-021 replaces. A regression test inside any of them would be deleted along
with them, and the refactor could hide the defect. So nothing here imports from
those suites.

**What reproducing the report found (2026-09-15).** The Record in the report is
seed_demo's `[DEMO] Declined by IERC, ITSO and KTTO preserved` (id 38 in the
dev database). The backend log shows the owner's first resubmission refused:
`POST /api/v1/reviews/resubmit/` returned 400 with a 77-byte body, which is
exactly `{"detail":"Please upload at least one updated document before
resubmitting."}`. The Record never left `declined`. The paper view kept showing
the IERC decline in both the clearance track and the review history, and the
refusal appeared as a small red line under the button. Seventeen seconds after
an upload, the second resubmission succeeded: IERC reset to pending, and ITSO
and KTTO stayed cleared and preserved. **So the clearance-aware transition
works. The upload guard (candidate 1) refused the resubmission, and the paper
view made the refusal look like a new decline.**

That is why this module has two tests, not one:

- **After an upload**, resubmission already behaves correctly. That test passes
  today and must keep passing through the cutover. Under a strict xfail it
  would pass unexpectedly and fail the build.
- **After a metadata-only revision**, the guard still refuses, because it
  accepts only an upload. ADR-021 §11 settles that "a new upload or an edit to
  the record's metadata" both count, and IR-260 is the cutover that implements
  it. That test carries the strict expected-failure marker, and IR-260 removes
  it.

**The rules for editing this module at the cutover.** The assertions describe
behaviour: the resubmission succeeds, the Record no longer awaits resubmission,
the office that asked for changes is pending again, and its peers are still
cleared and preserved. None of them names a pipeline stage. Only the setup
helpers, marked below, may change when IR-260 replaces the decline action with
a resubmission request. Do not edit an assertion to make either test pass.
"""

import shutil
import tempfile
from unittest import mock

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from rest_framework.test import APITestCase

from apps.accounts.models import Role, User
from apps.documents.models import UploadSlot
from apps.records.models import Record, RecordOwner, RecordType
from core.enums import PipelineStatus, RecordTypeName, RoleName

REVIEW_SUBMIT = "/api/v1/reviews/submit/"
RESUBMIT = "/api/v1/reviews/resubmit/"
DOCUMENT_SUBMIT = "/api/v1/documents/submit/"

#: The office that asks for changes in the reported case, and its two peers.
REQUESTING_OFFICE = "ierc"
PEER_OFFICES = ("itso", "ktto")


class SetupFailed(Exception):
    """
    A setup step did not produce the state the test needs.

    Deliberately not an `AssertionError`. The expected-failure marker below is
    limited to `AssertionError`, so a broken setup errors the test instead of
    being counted as the known defect.
    """


def _expect(response, status_code, step):
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
        cls.itso = user("ir233-itso@cit.edu", RoleName.ITSO)
        cls.ierc = user("ir233-ierc@cit.edu", RoleName.IERC)
        cls.ktto = user("ir233-ktto@cit.edu", RoleName.KTTO)

    # -- setup: may change at the IR-260 cutover ---------------------------

    def _decide(self, record, as_user, decision, comment=""):
        self.client.force_authenticate(as_user)
        return _expect(
            self.client.post(
                REVIEW_SUBMIT,
                {"record_id": record.pk, "status": decision, "comment": comment},
                format="json",
            ),
            201,
            f"{as_user.email} records {decision!r}",
        )

    def _project_where_one_office_asked_for_changes(self):
        """
        The reported Record: a Project that requested ITSO, IERC and KTTO.
        ITSO and KTTO have cleared, and IERC has asked for changes.
        """
        record_type = RecordType.objects.filter(name=RecordTypeName.PROJECT).first()
        if record_type is None:
            raise SetupFailed("RecordType 'Project' is not seeded; migrations incomplete")
        record = Record.objects.create(
            title="IR-233 regression",
            abstract="A" * 40,
            record_type=record_type,
            added_by=self.owner,
            pipeline_status=PipelineStatus.RDCO_INTAKE,
            requested_itso=True,
            requested_ierc=True,
            requested_ktto=True,
        )
        RecordOwner.objects.create(record=record, user=self.owner, is_primary=True)

        self._decide(record, self.rdco, "approved", "Routing to all three offices.")
        self._decide(record, self.itso, "approved", "Prior-art search complete.")
        self._decide(record, self.ktto, "approved", "Commercialisation potential noted.")
        self._decide(
            record, self.ierc, "declined",
            "Consent form for human participants is missing.",
        )

        if not self._awaits_resubmission(self._detail(record)):
            raise SetupFailed("the office's request for changes did not leave the Record awaiting resubmission")
        return record

    def _revise_by_uploading_a_document(self, record):
        slot = UploadSlot.objects.create(
            name="Ethics consent form", record_type=record.record_type
        )
        self.client.force_authenticate(self.owner)
        # Extraction is queued work, and this test is about the workflow.
        with mock.patch("apps.documents.tasks.extract_pdf_text.delay"):
            _expect(
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
        _expect(
            self.client.patch(
                f"/api/v1/records/{record.pk}/",
                {"abstract": "Revised to describe how participant consent is obtained. " * 2},
                format="json",
            ),
            200,
            "owner edits the record's metadata",
        )

    def _awaits_resubmission(self, detail):
        """
        Whether the owner still has to resubmit, read from the record detail.

        Today only `pipeline_status == "declined"` means that. IR-258 adds a
        computed `workflow_state` whose `awaiting_resubmission` value means it
        under the new model (ADR-021 §4), and `declined` then stops being
        stored. Reading whichever the API provides keeps the assertions
        unchanged across the cutover.
        """
        if "workflow_state" in detail:
            return detail["workflow_state"] == "awaiting_resubmission"
        return detail["pipeline_status"] == "declined"

    # -- observation: the API the frontend reads ---------------------------

    def _resubmit(self, record):
        self.client.force_authenticate(self.owner)
        return self.client.post(RESUBMIT, {"record_id": record.pk}, format="json")

    def _detail(self, record):
        self.client.force_authenticate(self.owner)
        return _expect(
            self.client.get(f"/api/v1/records/{record.pk}/"), 200, "owner reads the record"
        ).json()

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

        clearances = {c["office"]: c for c in detail["clearances"]}
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

    def test_resubmission_after_an_upload_resets_only_the_requesting_office(self):
        """The part of the report that already works. It must keep working through IR-260."""
        record = self._project_where_one_office_asked_for_changes()
        self._revise_by_uploading_a_document(record)

        response = self._resubmit(record)

        self._assert_clearance_aware_resubmission(record, response)

    @pytest.mark.xfail(
        strict=True,
        raises=AssertionError,
        reason=(
            "IR-233: resubmit_record accepts only a new upload as a revision, so a "
            "metadata-only revision is refused and the Record stays awaiting "
            "resubmission. ADR-021 §11 accepts an upload or a metadata edit; "
            "IR-260 implements that and removes this marker."
        ),
    )
    def test_resubmission_after_a_metadata_revision_resets_only_the_requesting_office(self):
        record = self._project_where_one_office_asked_for_changes()
        self._revise_metadata_only(record)

        response = self._resubmit(record)

        self._assert_clearance_aware_resubmission(record, response)
