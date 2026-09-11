"""A demonstrable workflow: seven accounts and a record in every pipeline state (IR-227).

    python manage.py seed_demo

Before this, the dev database held drafts and published records and nothing
else. Every reviewer-facing screen -- the review queue, the evaluation page,
the clearance track -- had nothing to show until somebody hand-drove a record
through the whole pipeline, or edited `pipeline_status` directly. A validation
rehearsal that begins with "first, let a developer fix the database" has already
failed the thing it was meant to measure.

**Everything here goes through the real services.** `lifecycle.apply`,
`approve_record`, `submit_clearance`, `reject_record` -- never an assignment to
`pipeline_status`. (`decline_record` is deliberately absent: it declines at a
*sequential* gate, and the only decline seeded here is IERC's, which is a
clearance decline and so goes through `submit_clearance`.) This is the constraint that makes the seed
worth anything: a seeder that writes statuses directly would cheerfully produce
states the transition table forbids, and the demo would then prove nothing about
the workflow it is supposed to demonstrate. If a scenario below cannot be built
by the real services, that is a finding about IRIS, and it should fail here
loudly rather than be faked into place.

**The flagship is `_scenario_declined_preserving_peers`.** ADR-003's
clearance-aware resubmission is the thesis contribution, and until now it had no
standing instance anyone could look at: showing it meant building the scenario by
hand every time. That record sits in `declined` with IERC declined and ITSO and
KTTO still `cleared`, so resubmitting it visibly resets one office and preserves
two. Upload a document as the student first -- `resubmit_record` requires one
since IR-139, and that refusal is part of the demo, not an obstacle to it.

Idempotent: records are keyed by title and skipped if present, so running twice
changes nothing. Refuses to run outside DEBUG without `--force`, because these
are known-password accounts and nothing good happens if they reach production.
"""

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from apps.accounts.models import Role, User
from apps.records import lifecycle
from apps.records.models import Record, RecordOwner, RecordType
from apps.reviews.services import approve_record, reject_record, submit_clearance
from core.enums import Office, RecordTypeName, ReviewDecision, RoleName

#: The six application roles, one account each. Emails match `seed_test_users`
#: so the two commands converge on the same accounts rather than competing.
DEMO_USERS = [
    ("iris-student@cit.edu", RoleName.STUDENT),
    ("iris-adviser@cit.edu", RoleName.ADVISER),
    ("iris-rdco@cit.edu", RoleName.RDCO),
    ("iris-itso@cit.edu", RoleName.ITSO),
    ("iris-ierc@cit.edu", RoleName.IERC),
    ("iris-ktto@cit.edu", RoleName.KTTO),
]

#: The seventh account, and the one that was missing.
#:
#: **Not an application role.** `core.permissions.ADMIN_ROLES` is `{RDCO}` --
#: RDCO *is* IRIS's administrator, holding account administration, the audit log
#: and the request queues. This account exists for the Django admin site only,
#: and IR-165 deliberately made `is_superuser` confer no API authorization, so it
#: can open /admin and nothing else. Seeding it with a role would quietly
#: recreate the privilege bypass that ticket removed.
ADMIN_EMAIL = "iris-admin@cit.edu"

#: Titles are the idempotency key, so they must be stable and unmistakable.
_PREFIX = "[DEMO]"


class Command(BaseCommand):
    help = "Seed demo accounts and one record in every pipeline state (IR-227)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--password", default="testpass123",
            help="Password for every demo account (default: testpass123).",
        )
        parser.add_argument(
            "--force", action="store_true",
            help="Seed even when DEBUG is off. These are known-password accounts.",
        )

    def handle(self, *args, **options):
        if not settings.DEBUG and not options["force"]:
            raise CommandError(
                "refusing to seed demo accounts with DEBUG off -- these have a "
                "known password. Pass --force if you are certain this is not "
                "production."
            )

        self.password = options["password"]
        users = self._seed_users()
        self._seed_records(users)

        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS("Demo data ready."))
        self.stdout.write(f"  Sign in at /login with password: {self.password}")
        self.stdout.write(
            f"  The preserved-clearance demo is the record titled "
            f"'{_PREFIX} Declined by IERC, ITSO and KTTO preserved'."
        )
        self.stdout.write(
            "  Upload a document as the student before resubmitting it -- "
            "resubmission requires one, by design."
        )

    # -- accounts ---------------------------------------------------------

    def _seed_users(self) -> dict[str, User]:
        users: dict[str, User] = {}
        for email, role_name in DEMO_USERS:
            role = Role.objects.get_or_create(name=role_name)[0]
            user, created = User.objects.get_or_create(
                email=email,
                defaults={"first_name": "Demo", "last_name": str(role_name)},
            )
            user.role = role
            user.is_verified = True
            user.is_active = True
            user.set_password(self.password)
            user.save()
            users[role_name] = user
            self._report(created, f"{email} -> {role_name}")

        admin, created = User.objects.get_or_create(
            email=ADMIN_EMAIL,
            defaults={"first_name": "Demo", "last_name": "Admin"},
        )
        # role stays None deliberately -- see ADMIN_EMAIL's docstring.
        admin.is_verified = True
        admin.is_active = True
        admin.is_staff = True
        admin.is_superuser = True
        admin.set_password(self.password)
        admin.save()
        self._report(created, f"{ADMIN_EMAIL} -> Django superuser (no application role)")

        return users

    # -- records ----------------------------------------------------------

    def _seed_records(self, users: dict[str, User]):
        scenarios = [
            self._scenario_draft,
            self._scenario_adviser_review,
            self._scenario_approved,
            self._scenario_completed,
            self._scenario_rdco_intake,
            self._scenario_itso_review,
            self._scenario_parallel_review,
            self._scenario_rdco_review,
            self._scenario_published,
            self._scenario_rejected,
            self._scenario_declined_preserving_peers,
        ]
        for scenario in scenarios:
            scenario(users)

    def _make(self, title, type_name, owner, **extra) -> Record | None:
        """Create a draft, or return None when this scenario is already seeded.

        Returning None rather than the existing record is deliberate: a caller
        that got the record back could go on to drive it through the pipeline a
        second time, which on an already-advanced record would raise
        `InvalidPipelineTransition` and break idempotency.
        """
        full_title = f"{_PREFIX} {title}"
        if Record.objects.filter(title=full_title).exists():
            self.stdout.write(f"  = {full_title} (already seeded)")
            return None

        record = Record.objects.create(
            title=full_title,
            abstract=(
                "Seeded by manage.py seed_demo to demonstrate this pipeline "
                "state. Not a real disclosure."
            ),
            record_type=RecordType.objects.get_or_create(name=type_name)[0],
            added_by=owner,
            pipeline_status=lifecycle.INITIAL_STATUS,
            **extra,
        )
        RecordOwner.objects.create(record=record, user=owner, is_primary=True)
        return record

    def _submit(self, record: Record, owner: User):
        """Submit as `RecordViewSet.submit` does, consent included.

        The view stamps DPA consent before transitioning (IR-226). Seeding
        through the service layer skips the view, so the stamp is applied here
        too -- a seeded record that reached a review queue with no consent
        behind it would misrepresent the very flow the demo exists to show.
        """
        record.dpa_accepted_at = timezone.now()
        record.dpa_accepted_by = owner
        record.save(update_fields=["dpa_accepted_at", "dpa_accepted_by", "updated_at"])
        lifecycle.apply(record, lifecycle.WorkflowEvent.SUBMIT, owner)

    # -- the scenarios ----------------------------------------------------

    @transaction.atomic
    def _scenario_draft(self, users):
        record = self._make(
            "Draft, never submitted", RecordTypeName.THESIS_RESEARCH, users[RoleName.STUDENT]
        )
        if record:
            self._done(record)

    @transaction.atomic
    def _scenario_adviser_review(self, users):
        record = self._make(
            "Awaiting adviser review", RecordTypeName.PROPOSAL, users[RoleName.STUDENT],
            adviser=users[RoleName.ADVISER],
        )
        if record:
            self._submit(record, users[RoleName.STUDENT])
            self._done(record)

    @transaction.atomic
    def _scenario_approved(self, users):
        record = self._make(
            "Proposal approved by adviser", RecordTypeName.PROPOSAL, users[RoleName.STUDENT],
            adviser=users[RoleName.ADVISER],
        )
        if record:
            self._submit(record, users[RoleName.STUDENT])
            approve_record(record, users[RoleName.ADVISER], "Looks good. Proceed.")
            self._done(record)

    @transaction.atomic
    def _scenario_completed(self, users):
        record = self._make(
            "Proposal completed", RecordTypeName.PROPOSAL, users[RoleName.STUDENT],
            adviser=users[RoleName.ADVISER],
        )
        if record:
            self._submit(record, users[RoleName.STUDENT])
            approve_record(record, users[RoleName.ADVISER], "Approved.")
            lifecycle.apply(record, lifecycle.WorkflowEvent.MARK_COMPLETE, users[RoleName.RDCO])
            self._done(record)

    @transaction.atomic
    def _scenario_rdco_intake(self, users):
        record = self._make(
            "Awaiting RDCO intake", RecordTypeName.THESIS_RESEARCH, users[RoleName.STUDENT],
            requested_ierc=True,
        )
        if record:
            self._submit(record, users[RoleName.STUDENT])
            self._done(record)

    @transaction.atomic
    def _scenario_itso_review(self, users):
        """ITSO and KTTO both act at `itso_review`; IERC only joins once ITSO clears."""
        record = self._make(
            "At ITSO clearance", RecordTypeName.PROJECT, users[RoleName.STUDENT],
            requested_itso=True, requested_ktto=True,
        )
        if record:
            self._submit(record, users[RoleName.STUDENT])
            approve_record(record, users[RoleName.RDCO], "Routing for clearance.")
            self._done(record)

    @transaction.atomic
    def _scenario_parallel_review(self, users):
        record = self._make(
            "At parallel clearance, ITSO cleared", RecordTypeName.PROJECT,
            users[RoleName.STUDENT],
            requested_itso=True, requested_ierc=True, requested_ktto=True,
        )
        if record:
            self._submit(record, users[RoleName.STUDENT])
            approve_record(record, users[RoleName.RDCO], "Routing for clearance.")
            submit_clearance(
                record, users[RoleName.ITSO], Office.ITSO, ReviewDecision.APPROVED,
                "No prior art conflict found.",
            )
            self._done(record)

    @transaction.atomic
    def _scenario_rdco_review(self, users):
        """Every requested office has cleared, so it waits on RDCO's final review."""
        record = self._make(
            "All offices cleared, awaiting RDCO", RecordTypeName.THESIS_RESEARCH,
            users[RoleName.STUDENT], requested_ierc=True,
        )
        if record:
            self._submit(record, users[RoleName.STUDENT])
            approve_record(record, users[RoleName.RDCO], "Routing to IERC.")
            submit_clearance(
                record, users[RoleName.IERC], Office.IERC, ReviewDecision.APPROVED,
                "Ethics clearance granted.",
            )
            self._done(record)

    @transaction.atomic
    def _scenario_published(self, users):
        """No offices requested, so intake goes straight to final review (ADR-018)."""
        record = self._make(
            "Published", RecordTypeName.THESIS_RESEARCH, users[RoleName.STUDENT]
        )
        if record:
            self._submit(record, users[RoleName.STUDENT])
            approve_record(record, users[RoleName.RDCO], "No office clearance required.")
            approve_record(record, users[RoleName.RDCO], "Published to the catalogue.")
            self._done(record)

    @transaction.atomic
    def _scenario_rejected(self, users):
        record = self._make(
            "Rejected at intake", RecordTypeName.THESIS_RESEARCH, users[RoleName.STUDENT]
        )
        if record:
            self._submit(record, users[RoleName.STUDENT])
            reject_record(
                record, users[RoleName.RDCO],
                "Out of scope for institutional disclosure.",
            )
            self._done(record)

    @transaction.atomic
    def _scenario_declined_preserving_peers(self, users):
        """**The thesis contribution, as a standing instance.**

        IERC declines while ITSO and KTTO have already cleared. Resubmitting
        resets IERC alone and preserves the other two -- ADR-003's
        clearance-aware resubmission, which is the one behaviour in IRIS that a
        reviewer most needs to see rather than be told about.

        Under the `RESTART_ALL` policy (IR-137/ADR-004) the same record resets
        all three instead, which is exactly the comparison the evaluation makes.
        """
        record = self._make(
            "Declined by IERC, ITSO and KTTO preserved", RecordTypeName.PROJECT,
            users[RoleName.STUDENT],
            requested_itso=True, requested_ierc=True, requested_ktto=True,
        )
        if not record:
            return

        self._submit(record, users[RoleName.STUDENT])
        approve_record(record, users[RoleName.RDCO], "Routing to all three offices.")
        submit_clearance(
            record, users[RoleName.ITSO], Office.ITSO, ReviewDecision.APPROVED,
            "Prior-art search complete; no conflict.",
        )
        submit_clearance(
            record, users[RoleName.KTTO], Office.KTTO, ReviewDecision.APPROVED,
            "Commercialisation potential noted.",
        )
        submit_clearance(
            record, users[RoleName.IERC], Office.IERC, ReviewDecision.DECLINED,
            "Consent form for human participants is missing. Please attach it "
            "and resubmit.",
        )
        self._done(record)

    # -- output -----------------------------------------------------------

    def _done(self, record: Record):
        record.refresh_from_db()
        self.stdout.write(
            self.style.SUCCESS(f"  + {record.title} -> {record.pipeline_status}")
        )

    def _report(self, created: bool, line: str):
        style = self.style.SUCCESS if created else self.style.NOTICE
        self.stdout.write(style(f"  {'+' if created else '='} {line}"))
