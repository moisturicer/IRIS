"""One seeder: accounts, the Discover catalogue, and a record in every pipeline state (IR-227).

    python manage.py seed_demo

**This replaces four separate seeders**, which between them used two account
namespaces and two passwords, and which had to be run in the right order by
hand through `manage.py shell <`:

    scripts/seed_demo_users.py       -> accounts (this file, phase 1)
    scripts/seed_demo_records.py     -> the Discover catalogue (phase 3)
    scripts/seed_demo_clearances.py  -> a record mid-clearance (phase 4)
    accounts/.../seed_test_users.py  -> a second, `iris-*` account set at a
                                        different password; deleted outright

The account convention here is the one that already existed -- `<role>@cit.edu`
at `IrisDemo123!`. Nothing about the credentials people already use has changed.

**Everything goes through the real services.** `lifecycle.apply`,
`approve_record`, `submit_clearance`, `reject_record`, `resubmit_record` --
never an assignment to `pipeline_status`. That is the point rather than a
style preference, and it is what the deleted scripts got wrong:
`seed_demo_records.py` wrote `record.pipeline_status = "published"` directly,
and `seed_demo_clearances.py` hand-built `Review` and `RecordClearance` rows and
then backdated their timestamps *past the ORM* to fake a preserved clearance.
Both produced states the workflow itself never produced, so neither proved
anything about the workflow -- and a faked state drifts silently the moment the
real routing changes.

**The two records that matter are the last two.**

`[DEMO] Declined by IERC, ITSO and KTTO preserved` sits in `declined` with ITSO
and KTTO cleared, waiting for the student to resubmit. That is the demo you
*drive*: upload a document, resubmit, and watch one office reset while two
survive.

`[DEMO] Resubmitted, ITSO and KTTO preserved` has already been through it, so
the paper view's "Preserved" badges render on arrival. This is what
`seed_demo_clearances.py` was for -- except that script set `pipeline_status`
and the clearance rows by hand and never set `last_resubmitted_at`, which is
what `preserved` is actually derived from (IR-139). Here the badge is a
consequence of a real resubmission, so it cannot disagree with the rule.

Idempotent: records are keyed by title and skipped if present. Accounts are
re-saved every run, so **re-running resets the seven passwords to the default** --
say so before a rehearsal if someone has changed one.

Refuses to run with `DEBUG` off unless `--force`, because these are
known-password accounts.
"""

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from apps.accounts.models import College, Course, Role, StudentProfile, User
from apps.documents.models import RecordUpload, UploadSlot
from apps.records import lifecycle
from apps.records.models import (
    Author,
    Classification,
    Record,
    RecordOwner,
    RecordType,
)
from apps.reviews.services import (
    approve_record,
    reject_record,
    resubmit_record,
    submit_clearance,
)
from core.enums import IPType, Office, RecordTypeName, ReviewDecision, RoleName

#: The convention that already existed, kept deliberately (see module docstring).
PASSWORD = "IrisDemo123!"

#: email, first, last, role
ROLE_ACCOUNTS = [
    ("student@cit.edu", "Sam", "Student", RoleName.STUDENT),
    ("adviser@cit.edu", "Ana", "Adviser", RoleName.ADVISER),
    ("rdco@cit.edu", "Rita", "Cruz", RoleName.RDCO),
    ("itso@cit.edu", "Ivan", "Santos", RoleName.ITSO),
    ("ierc@cit.edu", "Elena", "Reyes", RoleName.IERC),
    ("ktto@cit.edu", "Karl", "Tan", RoleName.KTTO),
]

#: The seventh account: **a Django superuser holding no application role.**
#:
#: `core.permissions.ADMIN_ROLES` is `{RDCO}` -- RDCO is IRIS's administrator,
#: holding account administration, the audit log and the request queues. This
#: account opens /admin and nothing else, because IR-165 deliberately left
#: `is_superuser` with no API standing. Giving it a role would look harmless and
#: quietly recreate the privilege bypass that ticket removed.
ADMIN_EMAIL = "admin@cit.edu"

CLASSIFICATIONS = [
    "Artificial Intelligence",
    "Internet of Things",
    "Clean Energy",
    "Healthcare & MedTech",
    "Cybersecurity",
    "Agriculture Technology",
]

#: The Discover catalogue. Owners are college-linked so the `college` filter --
#: which joins Record -> owners -> student_profile -> course -> department ->
#: college -- has something to match on.
#:
#: title, classification, type, year, is_ip, ip_type, commercial, extension, college, authors
CATALOGUE = [
    ("Retrieval-Augmented Generation for Institutional Research Discovery",
     "Artificial Intelligence", RecordTypeName.THESIS_RESEARCH, 2026, True, IPType.PATENT, True, False, "CCS",
     ["Sam Student", "Ana Adviser"]),
    ("A Low-Cost IoT Flood Sensor Network for Cebu Barangays",
     "Internet of Things", RecordTypeName.PROJECT, 2025, True, IPType.UTILITY_MODEL, True, True, "CEA",
     ["Miguel Torres", "Rita Cruz"]),
    ("Solar-Assisted Water Purification for Off-Grid Island Communities",
     "Clean Energy", RecordTypeName.THESIS_RESEARCH, 2025, False, "", False, True, "CEA",
     ["Liza Fernandez"]),
    ("Machine Learning Triage Support for Rural Health Units",
     "Healthcare & MedTech", RecordTypeName.THESIS_RESEARCH, 2024, True, IPType.COPYRIGHT, False, False, "CNAHS",
     ["Joy Ramirez", "Paolo Diaz"]),
    ("Phishing Resistance Training Outcomes Among University Staff",
     "Cybersecurity", RecordTypeName.THESIS_RESEARCH, 2024, False, "", False, False, "CCS",
     ["Karl Tan"]),
    ("Vision-Based Ripeness Grading for Smallholder Mango Farms",
     "Agriculture Technology", RecordTypeName.PROJECT, 2023, True, IPType.TRADE_SECRET, True, False, "CCS",
     ["Elena Reyes", "Ivan Santos"]),
    ("Blockchain-Backed Academic Credential Verification",
     "Cybersecurity", RecordTypeName.PROJECT, 2026, True, IPType.PATENT, True, False, "CCS",
     ["Noel Abad"]),
    ("Community Waste-to-Energy Feasibility in Metro Cebu",
     "Clean Energy", RecordTypeName.THESIS_RESEARCH, 2023, False, "", False, True, "CEA",
     ["Grace Lim", "Miguel Torres"]),
]

ABSTRACT = (
    "This study investigates {topic} within the context of Cebu Institute of "
    "Technology - University's institutional research programme. The work "
    "documents the design, implementation and evaluation of the proposed "
    "approach, reporting measured outcomes against a baseline and discussing "
    "the implications for adoption across the university and its partner "
    "communities. Limitations and directions for further work are outlined."
)

#: Titles are the idempotency key, so they must be stable and unmistakable.
_PREFIX = "[DEMO]"

FLAGSHIP_TITLE = f"{_PREFIX} Declined by IERC, ITSO and KTTO preserved"
RESUBMITTED_TITLE = f"{_PREFIX} Resubmitted, ITSO and KTTO preserved"


class Command(BaseCommand):
    help = "Seed demo accounts, the Discover catalogue, and every pipeline state (IR-227)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--password", default=PASSWORD,
            help=f"Password for every demo account (default: {PASSWORD}).",
        )
        parser.add_argument(
            "--force", action="store_true",
            help="Seed even when DEBUG is off. These are known-password accounts.",
        )
        parser.add_argument(
            "--accounts-only", action="store_true",
            help="Seed the seven accounts and stop. Replaces seed_demo_users.py.",
        )

    def handle(self, *args, **options):
        if not settings.DEBUG and not options["force"]:
            raise CommandError(
                "refusing to seed demo accounts with DEBUG off -- these have a "
                "known password. Pass --force if you are certain this is not "
                "production."
            )

        self.password = options["password"]
        users = self._seed_accounts()

        if not options["accounts_only"]:
            self._seed_classifications()
            self._seed_catalogue(users)
            self._seed_workflow(users)

        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS("Demo data ready."))
        self.stdout.write(f"  Every account signs in at /login with: {self.password}")
        if not options["accounts_only"]:
            self.stdout.write(f"  Drive the preservation demo on: '{FLAGSHIP_TITLE}'")
            self.stdout.write("    (upload a document as the student first -- resubmission requires one)")
            self.stdout.write(f"  Already-preserved badges render on: '{RESUBMITTED_TITLE}'")

    # -- phase 1: accounts -------------------------------------------------

    def _seed_accounts(self) -> dict[str, User]:
        users: dict[str, User] = {}
        for email, first, last, role_name in ROLE_ACCOUNTS:
            role = Role.objects.get_or_create(name=role_name)[0]
            user, created = User.objects.get_or_create(
                email=email, defaults={"first_name": first, "last_name": last},
            )
            user.first_name = first
            user.last_name = last
            user.role = role
            user.is_verified = True   # LoginView rejects unverified accounts
            user.is_active = True
            user.is_locked = False
            user.consent_given = True
            user.set_password(self.password)
            user.save()
            users[role_name] = user
            self._report(created, f"{email:22} role={role_name}")

        admin, created = User.objects.get_or_create(
            email=ADMIN_EMAIL, defaults={"first_name": "Iris", "last_name": "Admin"},
        )
        # role stays None deliberately -- see ADMIN_EMAIL's docstring.
        admin.is_staff = True
        admin.is_superuser = True
        admin.is_verified = True
        admin.is_active = True
        admin.set_password(self.password)
        admin.save()
        self._report(created, f"{ADMIN_EMAIL:22} Django superuser, no application role")

        return users

    # -- phase 2: reference data -------------------------------------------

    def _seed_classifications(self):
        for name in CLASSIFICATIONS:
            Classification.objects.get_or_create(name=name)
        self.stdout.write(f"  classifications: {Classification.objects.count()}")

    def _catalogue_owner(self, college_code, first, last) -> User:
        """A verified student whose course sits under `college_code`."""
        college = College.objects.filter(code=college_code).first()
        course = Course.objects.filter(department__college=college).first() if college else None

        email = f"{first.lower()}.{last.lower()}@cit.edu"
        user, _ = User.objects.get_or_create(
            email=email, defaults={"first_name": first, "last_name": last}
        )
        user.first_name = first
        user.last_name = last
        user.role = Role.objects.get_or_create(name=RoleName.STUDENT)[0]
        user.is_verified = True
        user.consent_given = True
        user.set_password(self.password)
        user.save()

        if course:
            StudentProfile.objects.update_or_create(user=user, defaults={"course": course})
        return user

    # -- phase 3: the Discover catalogue -----------------------------------

    def _seed_catalogue(self, users):
        """Published records, reached by being published rather than by assignment.

        `seed_demo_records.py` set `pipeline_status = "published"` directly. Two
        RDCO approvals get there legitimately -- intake, then final review --
        and a record that cannot make that journey is one Discover should not
        have been showing.
        """
        rdco = users[RoleName.RDCO]
        for (title, classification_name, type_name, year, is_ip, ip_type,
             commercial, extension, college_code, author_names) in CATALOGUE:

            if Record.objects.filter(title=title).exists():
                self.stdout.write(f"  = {title[:58]} (already seeded)")
                continue

            first, last = author_names[0].split()[0], author_names[0].split()[-1]
            owner = self._catalogue_owner(college_code, first, last)

            record = Record.objects.create(
                title=title,
                abstract=ABSTRACT.format(topic=classification_name.lower()),
                classification=Classification.objects.filter(name=classification_name).first(),
                record_type=RecordType.objects.get_or_create(name=type_name)[0],
                year_accomplished=year,
                is_ip=is_ip,
                ip_type=ip_type,
                for_commercialization=commercial,
                community_extension=extension,
                added_by=owner,
                pipeline_status=lifecycle.INITIAL_STATUS,
                access_count=(year - 2020) * 7 + len(title) % 13,
            )
            RecordOwner.objects.create(record=record, user=owner, is_primary=True)
            Author.objects.bulk_create([Author(record=record, name=n) for n in author_names])

            # No offices requested, so intake routes straight to final review.
            self._submit(record, owner)
            approve_record(record, rdco, "Intake complete; no office clearance required.")
            approve_record(record, rdco, "Published to the catalogue.")
            self._done(record)

    # -- phase 4: one record per pipeline state ----------------------------

    def _seed_workflow(self, users):
        for scenario in (
            self._scenario_draft,
            self._scenario_adviser_review,
            self._scenario_approved,
            self._scenario_completed,
            self._scenario_rdco_intake,
            self._scenario_itso_review,
            self._scenario_parallel_review,
            self._scenario_rdco_review,
            self._scenario_rejected,
            self._scenario_declined_preserving_peers,
            self._scenario_resubmitted_with_preserved_clearances,
        ):
            scenario(users)

    def _make(self, title, type_name, owner, **extra) -> Record | None:
        """Create a draft, or return None when this scenario is already seeded.

        Returning None rather than the existing record is deliberate: a caller
        that got the record back could drive it through the pipeline a second
        time, which on an already-advanced record raises
        `InvalidPipelineTransition` and breaks idempotency.
        """
        full_title = title if title.startswith(_PREFIX) else f"{_PREFIX} {title}"
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
        too -- a seeded record in a review queue with no consent behind it would
        misrepresent the flow the demo exists to show.
        """
        record.dpa_accepted_at = timezone.now()
        record.dpa_accepted_by = owner
        record.save(update_fields=["dpa_accepted_at", "dpa_accepted_by", "updated_at"])
        lifecycle.apply(record, lifecycle.WorkflowEvent.SUBMIT, owner)

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

    def _drive_to_ierc_decline(self, title, users) -> Record | None:
        """Two offices cleared, IERC declined. The shared setup for both demos."""
        record = self._make(
            title, RecordTypeName.PROJECT, users[RoleName.STUDENT],
            requested_itso=True, requested_ierc=True, requested_ktto=True,
        )
        if not record:
            return None

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
        return record

    @transaction.atomic
    def _scenario_declined_preserving_peers(self, users):
        """**The demo you drive.** ADR-003's contribution, waiting to be triggered.

        Sits in `declined`. Resubmit it and IERC alone resets while ITSO and
        KTTO survive. Under the `RESTART_ALL` policy (IR-137/ADR-004) the same
        record resets all three, which is the comparison the evaluation makes.
        """
        record = self._drive_to_ierc_decline(FLAGSHIP_TITLE, users)
        if record:
            self._done(record)

    @transaction.atomic
    def _scenario_resubmitted_with_preserved_clearances(self, users):
        """**The demo you look at.** The same case, already resubmitted.

        Replaces `seed_demo_clearances.py`, which built this shape by hand and
        backdated `Review.created_at` and `RecordClearance.updated_at` past the
        ORM. It also never set `last_resubmitted_at` -- and that is what
        `preserved` is derived from (IR-139), so the badge it advertised may not
        have rendered at all. Here the resubmission is real, so the badge is a
        consequence of the rule rather than an imitation of it.
        """
        record = self._drive_to_ierc_decline(RESUBMITTED_TITLE, users)
        if not record:
            return

        owner = users[RoleName.STUDENT]
        # Resubmission requires a document uploaded since the decline (IR-139).
        slot, _ = UploadSlot.objects.get_or_create(
            name="Revised ethics consent form", record_type=record.record_type
        )
        RecordUpload.objects.create(
            record=record, slot=slot, file="documents/demo-revised-consent.pdf",
            uploaded_by=owner,
        )
        resubmit_record(record, owner)
        self._done(record)

    # -- output ------------------------------------------------------------

    def _done(self, record: Record):
        record.refresh_from_db()
        self.stdout.write(
            self.style.SUCCESS(f"  + {record.title[:58]} -> {record.pipeline_status}")
        )

    def _report(self, created: bool, line: str):
        style = self.style.SUCCESS if created else self.style.NOTICE
        self.stdout.write(style(f"  {'+' if created else '='} {line}"))
