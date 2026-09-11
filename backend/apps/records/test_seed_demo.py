"""The demo seed produces states the workflow itself would produce (IR-227).

`seed_demo` exists so a validation rehearsal can start mid-workflow instead of
with a developer editing `pipeline_status` by hand. That only holds if the seed
is honest: a seeder that assigned statuses directly would happily manufacture
states the transition table forbids, and every reviewer screen would then be
demonstrating a fiction.

So the load-bearing test here is not "eleven records exist". It is
`test_the_flagship_record_actually_preserves_its_peer_clearances`, which takes
the seeded record and *resubmits it through the real service*, then checks the
outcome. If the seed had faked its way into `declined`, that resubmission would
route somewhere else or raise. It is the demo, executed.
"""
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, override_settings
from io import StringIO

from apps.accounts.models import User
from apps.documents.models import RecordUpload, UploadSlot
from apps.reviews.models import RecordClearance
from apps.reviews.services import resubmit_record
from core.enums import ClearanceStatus, Office, PipelineStatus

from .management.commands.seed_demo import ADMIN_EMAIL, DEMO_USERS, _PREFIX
from .models import Record

FLAGSHIP = f"{_PREFIX} Declined by IERC, ITSO and KTTO preserved"


#: PBKDF2 is deliberately slow, and `seed_demo` hashes seven passwords per run
#: while `SeedDemoRecordTests` reseeds for every test. Left at the default this
#: module alone accounted for minutes of the suite -- confirmed by interrupting
#: a wedged run and landing in `django/utils/crypto.py`. Nothing here asserts
#: anything about hashing, so a cheap hasher costs no coverage.
FAST_HASHER = ["django.contrib.auth.hashers.MD5PasswordHasher"]


def seed(**kwargs):
    """Run the command, swallowing its narration.

    `force=True` by default because **Django forces `DEBUG = False` in tests**,
    so the production guard fires on every call. The guard itself is exercised
    deliberately in `SeedDemoGuardTests` rather than tripped over here.
    """
    kwargs.setdefault("force", True)
    call_command("seed_demo", stdout=StringIO(), **kwargs)


@override_settings(PASSWORD_HASHERS=FAST_HASHER)
class SeedDemoGuardTests(TestCase):
    """The refusal that keeps known-password accounts out of production."""

    def test_it_refuses_to_run_with_debug_off(self):
        # No `override_settings(DEBUG=False)`: the test runner already forces
        # it off, and writing it here would suggest this test sets up a
        # condition it merely inherits.
        with self.assertRaises(CommandError):
            call_command("seed_demo", stdout=StringIO())
        self.assertFalse(User.objects.filter(email=ADMIN_EMAIL).exists())

    def test_the_refusal_names_the_way_past_it(self):
        """An operator who meant it should not have to read the source."""
        with self.assertRaises(CommandError) as caught:
            call_command("seed_demo", stdout=StringIO())
        self.assertIn("--force", str(caught.exception))

    def test_force_overrides_the_refusal(self):
        seed(force=True)
        self.assertTrue(User.objects.filter(email=ADMIN_EMAIL).exists())


@override_settings(PASSWORD_HASHERS=FAST_HASHER)
class SeedDemoAccountTests(TestCase):

    def test_it_seeds_all_seven_accounts(self):
        seed()
        for email, _role in DEMO_USERS:
            self.assertTrue(
                User.objects.filter(email=email).exists(), f"{email} was not seeded"
            )
        self.assertTrue(User.objects.filter(email=ADMIN_EMAIL).exists())

    def test_the_admin_is_a_django_superuser_with_no_application_role(self):
        """IR-165 reserved `is_superuser` for /admin and gave it no API standing.

        Seeding this account *with* a role -- RDCO, say -- would look harmless
        and would quietly hand a superuser application privileges too, which is
        the exact bypass that ticket removed. `ADMIN_ROLES` is `{RDCO}`: RDCO is
        already IRIS's administrator, and this account is a different thing.
        """
        seed()
        admin = User.objects.get(email=ADMIN_EMAIL)
        self.assertTrue(admin.is_superuser)
        self.assertTrue(admin.is_staff)
        self.assertIsNone(admin.role, "the demo superuser must hold no application role")


@override_settings(PASSWORD_HASHERS=FAST_HASHER)
class SeedDemoRecordTests(TestCase):

    #: Every state a reviewer or owner can be looking at. `pending_delete` is
    #: deliberately absent: it is reached through the delete-request queue,
    #: which has its own seeded fixtures and is not part of the disclosure
    #: workflow this seed demonstrates.
    EXPECTED_STATUSES = [
        PipelineStatus.DRAFT,
        PipelineStatus.ADVISER_REVIEW,
        PipelineStatus.APPROVED,
        PipelineStatus.COMPLETED,
        PipelineStatus.RDCO_INTAKE,
        PipelineStatus.ITSO_REVIEW,
        PipelineStatus.PARALLEL_REVIEW,
        PipelineStatus.RDCO_REVIEW,
        PipelineStatus.PUBLISHED,
        PipelineStatus.REJECTED,
        PipelineStatus.DECLINED,
    ]

    def setUp(self):
        seed()

    def test_every_pipeline_state_has_a_record(self):
        seeded = Record.objects.filter(title__startswith=_PREFIX)
        present = set(seeded.values_list("pipeline_status", flat=True))
        missing = [s for s in self.EXPECTED_STATUSES if s not in present]
        self.assertFalse(
            missing,
            f"no seeded record sits at {missing} -- a rehearsal cannot start there",
        )

    def test_submitted_records_carry_dpa_consent(self):
        """The seed must not manufacture records that skipped the consent gate.

        `submit()` stamps consent (IR-226); the seed drives the service layer
        directly, so it stamps it too. A seeded record past `draft` with no
        consent would misrepresent the flow being demonstrated.
        """
        past_draft = Record.objects.filter(title__startswith=_PREFIX).exclude(
            pipeline_status=PipelineStatus.DRAFT
        )
        self.assertTrue(past_draft.exists())
        for record in past_draft:
            self.assertIsNotNone(
                record.dpa_accepted_at,
                f"{record.title} reached {record.pipeline_status} without consent",
            )

    def test_running_twice_changes_nothing(self):
        before = Record.objects.filter(title__startswith=_PREFIX).count()
        statuses_before = dict(
            Record.objects.filter(title__startswith=_PREFIX).values_list("title", "pipeline_status")
        )

        seed()  # again

        after = Record.objects.filter(title__startswith=_PREFIX).count()
        self.assertEqual(before, after, "a second run duplicated records")
        self.assertEqual(
            statuses_before,
            dict(Record.objects.filter(title__startswith=_PREFIX).values_list("title", "pipeline_status")),
            "a second run advanced records that were already seeded",
        )

    def test_the_flagship_starts_declined_with_two_offices_cleared(self):
        record = Record.objects.get(title=FLAGSHIP)
        self.assertEqual(record.pipeline_status, PipelineStatus.DECLINED)

        by_office = {
            c.office: c.status
            for c in RecordClearance.objects.filter(record=record)
        }
        self.assertEqual(by_office[Office.ITSO], ClearanceStatus.CLEARED)
        self.assertEqual(by_office[Office.KTTO], ClearanceStatus.CLEARED)
        self.assertEqual(by_office[Office.IERC], ClearanceStatus.DECLINED)

    def test_the_flagship_record_actually_preserves_its_peer_clearances(self):
        """**The demo, executed.** ADR-003's contribution, on the seeded record.

        This is what makes the rest of this file worth anything. Resubmitting
        runs the real `resubmit_record`, which reads the declining stage off the
        last `Review` row -- so if the seed had reached `declined` by assigning
        the status rather than by having IERC decline, there would be no such
        row and this would route as a full restart instead.
        """
        record = Record.objects.get(title=FLAGSHIP)
        # `owners` is the reverse of RecordOwner.record, so a row rather than a
        # User -- the ownership link carries `is_primary` alongside the person.
        owner = record.owners.get(is_primary=True).user

        # Resubmission requires a document uploaded since the decline (IR-139).
        # That refusal is part of the demo; here it is simply satisfied.
        slot = UploadSlot.objects.create(
            name="Revised ethics consent form", record_type=record.record_type
        )
        RecordUpload.objects.create(
            record=record, slot=slot, file="documents/demo-revision.pdf",
            uploaded_by=owner,
        )

        resubmit_record(record, owner)

        record.refresh_from_db()
        by_office = {
            c.office: c.status
            for c in RecordClearance.objects.filter(record=record)
        }
        self.assertEqual(
            by_office[Office.ITSO], ClearanceStatus.CLEARED,
            "ITSO's completed clearance must survive the resubmission",
        )
        self.assertEqual(
            by_office[Office.KTTO], ClearanceStatus.CLEARED,
            "KTTO's completed clearance must survive the resubmission",
        )
        self.assertEqual(
            by_office[Office.IERC], ClearanceStatus.PENDING,
            "only the declining office is reset",
        )
        self.assertEqual(
            record.pipeline_status, PipelineStatus.PARALLEL_REVIEW,
            "the record returns to the stage IERC reviews at, not to the top",
        )
