"""
The people and objects the authorization matrix acts on (IR-615).

Built once for the whole matrix, from the shapes `seed_demo` already builds:
its six role accounts and its role-less superuser keep their emails, and the
in-review record is driven through the real acts -- `enter_at_adviser`, the
Adviser's `accept_and_route`, ITSO opening its seat -- exactly as
`seed_demo._scenario_new_model_at_rdco` does, stopping while ITSO reviews.
Nothing is written into a workflow table by hand that a real act would have
written, so a cell's outcome is the outcome a real record in that state gets.

Three accounts are added to seed_demo's, because the matrix needs a role in
more than one relation to the record: a second Student with no claim on
anything, a second ITSO member sitting in the pool unseated, and an ITSO
coordinator who is seated nowhere.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone

from apps.accounts.models import Role, User
from apps.documents.models import RecordFile, RecordUpload, UploadSlot, UploadStatus
from apps.documents.requests import ItemSpec, create_request, requesting_party
from apps.records.download_tokens import make_download_token
from apps.records.management.commands.seed_demo import ADMIN_EMAIL, ROLE_ACCOUNTS
from apps.records.models import DeleteRequest, DownloadRequest, Record, RecordOwner, RecordType
from apps.reviews import revisions, seats
from apps.reviews.models import ReviewComment, ReviewerSeat
from apps.reviews.routing import accept_and_route, enter_at_adviser
from core.enums import Party, PipelineStatus, RecordTypeName, RequestStatus, RoleName

#: The matrix's columns, in the order every table row lists them.
ROLES = (
    "anon",         # no credentials at all
    "other",        # a signed-in Student with no claim on anything here
    "owner",        # the Student who owns the record
    "adviser",      # the record's assigned Adviser, who routed it to ITSO
    "seated",       # an ITSO reviewer holding an open, opened seat on it
    "unseated",     # an ITSO member in the pool, with no seat on it
    "coordinator",  # an ITSO coordinator, seated nowhere
    "rdco",         # RDCO, IRIS's administrator role, seated nowhere
    "admin",        # a Django superuser with no application role (IR-165)
)

#: An id no fixture has. Every object route is also fired with each of its ids
#: replaced by this one, and a refusal must read exactly like that response.
MISSING_PK = 2_000_000_000

PDF_BYTES = b"%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF\n"


def pdf(name="paper.pdf") -> SimpleUploadedFile:
    """A fresh upload each call: a request consumes the file it is sent."""
    return SimpleUploadedFile(name, PDF_BYTES, content_type="application/pdf")


@dataclass
class World:
    users: dict[str, User | None]
    objects: dict[str, object] = field(default_factory=dict)
    #: The JWT a redeem link carries, for the approved download request.
    download_token: str = ""

    def value(self, name: str, attr: str = "pk"):
        return getattr(self.objects[name], attr)

    def record_of(self, name: str) -> Record:
        """The Record whose visibility governs knowing `name` exists."""
        obj = self.objects[name]
        if isinstance(obj, Record):
            return obj
        if isinstance(obj, ReviewerSeat):
            return obj.assignment.record
        if hasattr(obj, "record"):
            return obj.record
        return obj.request.record   # a document-request item

    def restore_files(self) -> None:
        """
        Put back any fixture file a request removed from storage.

        A cell's database writes are rolled back, but a file deleted from disk
        is not: once an office's `DELETE files/<id>/` has run, the row comes
        back and its file does not, and every later read of it is a 500.
        """
        from django.core.files.base import ContentFile
        from django.db.models.fields.files import FieldFile

        for obj in self.objects.values():
            for model_field in obj._meta.concrete_fields:
                value = getattr(obj, model_field.attname, None)
                if isinstance(value, FieldFile) and value.name and not value.storage.exists(value.name):
                    value.storage.save(value.name, ContentFile(PDF_BYTES))

    def can_see(self, role: str, name: str) -> bool:
        """Is `name`'s Record in `visible_to()` for `role`? (IR-153)"""
        user = self.users[role]
        obj = self.objects[name]
        from apps.ai.models import AskRun, Conversation, ResearchRun
        from apps.notifications.models import Notification
        if isinstance(obj, (AskRun, Conversation, ResearchRun)):
            return user is not None and obj.user_id == user.pk
        if isinstance(obj, Notification):
            return user is not None and Notification.objects.visible_to(user).filter(pk=obj.pk).exists()
        from rest_framework_simplejwt.token_blacklist.models import OutstandingToken
        if isinstance(obj, OutstandingToken):
            return role == "rdco"
        if isinstance(obj, User):
            return role == "rdco"
        from apps.accounts.models import RoleRequest
        if isinstance(obj, RoleRequest):
            return role == "rdco"
        from apps.opportunities.models import Opportunity
        if isinstance(obj, Opportunity):
            return user is not None
        return Record.objects.visible_to(user).filter(pk=self.record_of(name).pk).exists()


def _user(email, role_name, first="Test", last="User", **extra) -> User:
    role = Role.objects.get_or_create(name=role_name)[0] if role_name else None
    return User.objects.create_user(
        email=email, password="IrisDemo123!", first_name=first, last_name=last,
        role=role, is_verified=True, consent_given=True, **extra,
    )


def _users() -> dict[str, User | None]:
    seeded = {
        role: _user(email, role, first, last) for email, first, last, role in ROLE_ACCOUNTS
    }
    admin = _user(ADMIN_EMAIL, None, "Iris", "Admin", is_staff=True, is_superuser=True)
    return {
        "anon": None,
        "other": _user("other-student@cit.edu", RoleName.STUDENT),
        "owner": seeded[RoleName.STUDENT],
        "adviser": seeded[RoleName.ADVISER],
        "seated": seeded[RoleName.ITSO],
        "unseated": _user("itso-pool@cit.edu", RoleName.ITSO),
        "coordinator": _user("itso-coordinator@cit.edu", RoleName.ITSO, is_office_coordinator=True),
        "rdco": seeded[RoleName.RDCO],
        "admin": admin,
    }


def _record(title, owner, adviser=None, *, status=PipelineStatus.DRAFT, **extra) -> Record:
    record = Record.objects.create(
        title=title, abstract="A" * 60,
        record_type=RecordType.objects.get_or_create(name=RecordTypeName.THESIS_RESEARCH)[0],
        added_by=owner, adviser=adviser, pipeline_status=status,
        abstract_file=pdf(), **extra,
    )
    RecordOwner.objects.create(record=record, user=owner, is_primary=True)
    return record


def _at_itso(title, users) -> Record:
    """A Thesis the Adviser accepted and routed to ITSO, whose reviewer opened it."""
    owner, adviser, itso = users["owner"], users["adviser"], users["seated"]
    record = _record(
        title, owner, adviser, requested_itso=True,
        dpa_accepted_at=timezone.now(), dpa_accepted_by=owner,
    )
    entry = enter_at_adviser(record, owner)
    seats.open_review(entry.seats.get(), adviser)
    accept_and_route(
        record, adviser, to=[{"party": Party.ITSO, "nominee": itso.pk}],
        reason="The method may be patentable.",
    )
    seat = ReviewerSeat.objects.get(
        assignment__record=record, assignment__party=Party.ITSO, reviewer=itso,
    )
    seats.open_review(seat, itso)
    record.refresh_from_db()
    return record


def build_world() -> World:
    users = _users()
    owner, other, itso = users["owner"], users["other"], users["seated"]
    world = World(users=users)
    o = world.objects

    # -- the record under review, and everything hanging off it ----------
    o["record"] = record = _at_itso("Matrix: a Thesis at ITSO", users)
    o["slot"] = slot = UploadSlot.objects.create(name="Endorsement", record_type=record.record_type)
    o["upload"] = RecordUpload.objects.create(
        record=record, slot=slot, file=pdf("endorsement.pdf"), uploaded_by=owner,
    )
    o["upload_status"] = UploadStatus.objects.get_or_create(name="Reviewed")[0]
    o["record_file"] = RecordFile.objects.create(
        record=record, file=pdf("itso-note.pdf"), filename="itso-note.pdf",
        uploaded_by=itso, party=Party.ITSO,
    )
    o["document_request"] = document_request = create_request(
        record, itso, party=requesting_party(record, itso, Party.ITSO),
        message="Please attach the signed endorsement.",
        specs=[ItemSpec(slot=slot, label="")],
    )
    o["document_request_item"] = document_request.items.get()

    o["version"] = record.versions.get(number=1)
    # The owner's, so only the owner may edit it (IR-419).
    o["review_comment"] = ReviewComment.objects.create(
        record=record, author=owner, body="Is the endorsement enough?", version=o["version"],
    )

    # -- a record still at its Adviser's step, with the review opened ----
    # The acts that happen there (accept & route, decide) are fired on this
    # one: on `record` the Adviser's part is over, so a refusal there would
    # say "not now", not "not you".
    o["at_adviser"] = at_adviser = _record(
        "Matrix: a Thesis at its Adviser", owner, users["adviser"], requested_itso=True,
        dpa_accepted_at=timezone.now(), dpa_accepted_by=owner,
    )
    seats.open_review(enter_at_adviser(at_adviser, owner).seats.get(), users["adviser"])

    # -- a record ITSO asked to be revised --------------------------------
    o["revising"] = revising = _at_itso("Matrix: a Thesis awaiting revision", users)
    o["revision_request"] = revisions.request_revision(revising, itso, reason="Cite the prior art.")

    # -- the public catalogue and the request queues ---------------------
    o["published"] = published = _record(
        "Matrix: a published Thesis", owner, users["adviser"], status=PipelineStatus.PUBLISHED,
    )
    o["download_request"] = DownloadRequest.objects.create(
        record=published, requested_by=other,
    )
    approved = DownloadRequest.objects.create(
        record=published, requested_by=other,
        status=RequestStatus.APPROVED,
    )
    world.download_token = make_download_token(
        download_request_id=approved.pk, record_id=published.pk, user_id=other.pk,
    )
    pending = _record(
        "Matrix: a Thesis its owner asked to delete", owner, users["adviser"],
        status=PipelineStatus.PENDING_DELETE,
    )
    o["delete_request"] = DeleteRequest.objects.create(
        record=pending, requested_by=owner, previous_pipeline_status=PipelineStatus.PUBLISHED,
    )
    from datetime import timedelta
    from apps.accounts.models import RoleRequest, SystemSetting
    from apps.ai.models import AskRun, Conversation, ResearchRun, Turn
    from apps.notifications.models import Notification, NotificationType
    from apps.opportunities.models import Opportunity
    from rest_framework_simplejwt.tokens import RefreshToken
    from rest_framework_simplejwt.token_blacklist.models import OutstandingToken
    token = RefreshToken.for_user(other)
    o["session_token"] = OutstandingToken.objects.get(jti=token["jti"])
    o["reviewer_target"] = users["unseated"]
    o["target_user"] = users["other"]
    o["role_request"] = RoleRequest.objects.create(user=other, requested_role=users["adviser"].role)
    SystemSetting.objects.get_or_create(key="matrix-setting", defaults={"value": "test"})
    o["assignment"] = record.assignments.get(party=Party.ITSO)
    o["seat"] = o["assignment"].seats.get(reviewer=itso)
    o["conversation"] = Conversation.objects.create(user=owner, title="Private matrix conversation")
    o["turn"] = Turn.objects.create(conversation=o["conversation"], question="PRIVATE_TURN_QUESTION",
                                    answer="PRIVATE_TURN_ANSWER", state="no_sources")
    o["ask_run"] = AskRun.objects.create(
        user=owner, conversation=o["conversation"], state="cancelled",
        deadline_at=timezone.now()+timedelta(minutes=1),
    )
    o["research_run"] = ResearchRun.objects.create(user=owner, conversation=o["conversation"])
    o["notification"] = Notification.objects.create(
        recipient=owner, notif_type=NotificationType.objects.first(), message="Private matrix notification",
    )
    o["other_notification"] = Notification.objects.create(
        recipient=other, notif_type=NotificationType.objects.first(), message="Other reader notification",
    )
    o["student_broadcast"] = Notification.objects.create(
        broadcast_to_role=owner.role, notif_type=NotificationType.objects.first(), message="Student broadcast",
    )
    o["office_broadcast"] = Notification.objects.create(
        broadcast_to_role=itso.role, notif_type=NotificationType.objects.first(), message="ITSO broadcast",
    )
    o["opportunity"] = Opportunity.objects.create(
        title="Matrix opportunity", due_date=timezone.now().date()+timedelta(days=10),
        posted_by=users["rdco"], opportunity_type="internal_call", posting_office="RDCO",
    )
    o["adviser_opportunity"] = Opportunity.objects.create(
        title="Adviser's matrix opportunity", due_date=timezone.now().date()+timedelta(days=10),
        posted_by=users["adviser"], opportunity_type="internal_call", posting_office="Adviser",
    )
    return world
