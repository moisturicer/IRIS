"""The demo seed produces states the workflow itself would produce (IR-227).

`seed_demo` exists so a validation rehearsal can start mid-workflow instead of
with a developer editing `pipeline_status` by hand. That only holds if the seed
is honest: a seeder that assigned statuses directly would manufacture states the
transition table forbids, and every reviewer screen would then be demonstrating
a fiction. The four seeders this command replaced did exactly that --
`seed_demo_records.py` assigned `"published"`, and `seed_demo_clearances.py`
hand-built `Review` rows and backdated them past the ORM.

So the load-bearing tests here are not "records exist". They are the two that
take seeded records and *run the real service over them*:
`test_the_flagship_record_actually_preserves_its_peer_clearances` and
`test_the_resubmitted_record_shows_preserved_clearances`. If the seed had faked
its way into `declined`, there would be no `Review` row naming the declining
office and both would route as a full restart instead.
"""
from io import StringIO

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, override_settings

from apps.accounts.models import User
from apps.documents.models import RecordUpload, UploadSlot
from apps.reviews.models import RecordClearance
from apps.reviews.services import resubmit_record
from core.enums import ClearanceStatus, Office, PipelineStatus

from .management.commands.seed_demo import (
    ADMIN_EMAIL,
    FLAGSHIP_TITLE,
    PASSWORD,
    RESUBMITTED_TITLE,
    ROLE_ACCOUNTS,
    _PREFIX,
)
from .models import Record

#: PBKDF2 is deliberately slow, and `seed_demo` hashes a password for every
#: account on every run while these classes reseed per test. Left at the default
#: this module alone accounted for minutes of the suite -- confirmed by
#: interrupting a wedged run and landing in `django/utils/crypto.py`. Nothing
#: here asserts anything about hashing, so a cheap hasher costs no coverage.
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
        # No `override_settings(DEBUG=False)`: the test runner already forces it
        # off, and writing it here would suggest this test sets up a condition
        # it merely inherits.
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
        seed(accounts_only=True)
        for email, _first, _last, _role in ROLE_ACCOUNTS:
            self.assertTrue(
                User.objects.filter(email=email).exists(), f"{email} was not seeded"
            )
        self.assertTrue(User.objects.filter(email=ADMIN_EMAIL).exists())

    def test_it_keeps_the_account_convention_that_already_existed(self):
        """`<role>@cit.edu` at `IrisDemo123!`, from the deleted seed_demo_users.py.

        This command absorbed four seeders. Had it imposed its own emails or
        password, every existing demo note, screenshot and muscle memory would
        have silently stopped working -- so the convention is pinned here rather
        than left to whoever edits the constants next.
        """
        seed(accounts_only=True)
        self.assertEqual(PASSWORD, "IrisDemo123!")
        for email, _first, _last, _role in ROLE_ACCOUNTS:
            self.assertTrue(email.endswith("@cit.edu"))
            self.assertTrue(
                User.objects.get(email=email).check_password(PASSWORD),
                f"{email} does not accept the documented password",
            )

    def test_the_admin_is_a_django_superuser_with_no_application_role(self):
        """IR-165 reserved `is_superuser` for /admin and gave it no API standing.

        Seeding this account *with* a role -- RDCO, say -- would look harmless
        and would quietly hand a superuser application privileges too, which is
        the exact bypass that ticket removed. `ADMIN_ROLES` is `{RDCO}`: RDCO is
        already IRIS's administrator, and this account is a different thing.
        """
        seed(accounts_only=True)
        admin = User.objects.get(email=ADMIN_EMAIL)
        self.assertTrue(admin.is_superuser)
        self.assertTrue(admin.is_staff)
        self.assertIsNone(admin.role, "the demo superuser must hold no application role")

    def test_accounts_only_seeds_no_records(self):
        seed(accounts_only=True)
        self.assertFalse(Record.objects.exists())


@override_settings(PASSWORD_HASHERS=FAST_HASHER)
class SeedDemoRecordTests(TestCase):

    #: Every state a reviewer or owner can be looking at. `pending_delete` is
    #: deliberately absent: it is reached through the delete-request queue,
    #: which is not part of the disclosure workflow this seed demonstrates.
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
        present = set(Record.objects.values_list("pipeline_status", flat=True))
        missing = [s for s in self.EXPECTED_STATUSES if s not in present]
        self.assertFalse(
            missing,
            f"no seeded record sits at {missing} -- a rehearsal cannot start there",
        )

    def test_the_catalogue_reaches_published_through_the_workflow(self):
        """Discover's records are published, not assigned to `published`.

        `seed_demo_records.py` set the status directly, so a record Discover
        showed might never have been able to make the journey. Two RDCO
        approvals is the journey; a `Review` row for each is the evidence it
        happened.
        """
        published = Record.objects.filter(
            pipeline_status=PipelineStatus.PUBLISHED
        ).exclude(title__startswith=_PREFIX)
        self.assertTrue(published.exists(), "the Discover catalogue is empty")
        for record in published:
            self.assertGreaterEqual(
                record.reviews.count(), 2,
                f"{record.title} is published with no review history behind it",
            )

    def test_submitted_records_carry_dpa_consent(self):
        """The seed must not manufacture records that skipped the consent gate.

        `submit()` stamps consent (IR-226); the seed drives the service layer
        directly, so it stamps it too. A seeded record past `draft` with no
        consent would misrepresent the flow being demonstrated.
        """
        past_draft = Record.objects.exclude(pipeline_status=PipelineStatus.DRAFT)
        self.assertTrue(past_draft.exists())
        for record in past_draft:
            self.assertIsNotNone(
                record.dpa_accepted_at,
                f"{record.title} reached {record.pipeline_status} without consent",
            )

    def test_running_twice_changes_nothing(self):
        before = dict(Record.objects.values_list("title", "pipeline_status"))

        seed()  # again

        self.assertEqual(
            before,
            dict(Record.objects.values_list("title", "pipeline_status")),
            "a second run duplicated records or advanced ones already seeded",
        )

    def test_the_flagship_starts_declined_with_two_offices_cleared(self):
        record = Record.objects.get(title=FLAGSHIP_TITLE)
        self.assertEqual(record.pipeline_status, PipelineStatus.DECLINED)
        self.assertEqual(self._clearances(record), {
            Office.ITSO: ClearanceStatus.CLEARED,
            Office.KTTO: ClearanceStatus.CLEARED,
            Office.IERC: ClearanceStatus.DECLINED,
        })

    def test_the_flagship_record_actually_preserves_its_peer_clearances(self):
        """**The demo, executed.** ADR-003's contribution, on the seeded record.

        Resubmitting runs the real `resubmit_record`, which reads the declining
        stage off the last `Review` row -- so if the seed had reached `declined`
        by assigning the status rather than by having IERC decline, there would
        be no such row and this would route as a full restart instead.
        """
        record = Record.objects.get(title=FLAGSHIP_TITLE)
        owner = record.owners.get(is_primary=True).user

        # Resubmission requires a document uploaded since the decline (IR-139).
        # That refusal is part of the demo; here it is simply satisfied.
        slot, _ = UploadSlot.objects.get_or_create(
            name="Revised ethics consent form", record_type=record.record_type
        )
        RecordUpload.objects.create(
            record=record, slot=slot, file="documents/demo-revision.pdf",
            uploaded_by=owner,
        )

        resubmit_record(record, owner)

        record.refresh_from_db()
        self.assertEqual(self._clearances(record), {
            Office.ITSO: ClearanceStatus.CLEARED,
            Office.KTTO: ClearanceStatus.CLEARED,
            Office.IERC: ClearanceStatus.PENDING,
        }, "only the declining office is reset")
        self.assertEqual(
            record.pipeline_status, PipelineStatus.PARALLEL_REVIEW,
            "the record returns to the stage IERC reviews at, not to the top",
        )

    def test_the_resubmitted_record_shows_preserved_clearances(self):
        """What `seed_demo_clearances.py` was for, produced legitimately.

        That script set `pipeline_status` and the clearance rows by hand and
        backdated their timestamps past the ORM -- but never set
        `last_resubmitted_at`, which is what `preserved` is derived from
        (IR-139), so the badge it advertised may not have rendered at all.
        Here the resubmission is real, so `last_resubmitted_at` is set and the
        two surviving clearances were decided before it.
        """
        record = Record.objects.get(title=RESUBMITTED_TITLE)

        self.assertEqual(record.pipeline_status, PipelineStatus.PARALLEL_REVIEW)
        self.assertEqual(record.resubmission_count, 1)
        self.assertIsNotNone(
            record.last_resubmitted_at,
            "`preserved` is derived from this; without it no badge renders",
        )
        self.assertEqual(self._clearances(record), {
            Office.ITSO: ClearanceStatus.CLEARED,
            Office.KTTO: ClearanceStatus.CLEARED,
            Office.IERC: ClearanceStatus.PENDING,
        })
        for clearance in RecordClearance.objects.filter(
            record=record, status=ClearanceStatus.CLEARED
        ):
            self.assertLess(
                clearance.updated_at, record.last_resubmitted_at,
                f"{clearance.office} was decided after the resubmission, so it "
                "was re-granted rather than preserved",
            )

    def _clearances(self, record) -> dict:
        return {
            c.office: c.status
            for c in RecordClearance.objects.filter(record=record)
        }
