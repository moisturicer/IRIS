"""
An accepted Proposal continues as a new Thesis or Project record (IR-417;
ADR-032 §6).

The child is an ordinary `draft` that points back at its Proposal through
`derived_from`. From there it is published like any other draft: the owner
uploads the full manuscript in Publish and submits, and it enters at its
Adviser (§1). **The Proposal is never written**: its versions, reviews and
discussion stay on it, and nothing here saves it.
"""

from django.db import IntegrityError, transaction

from core.enums import PipelineStatus, RecordTypeName
from core.permissions import is_record_owner

from . import lifecycle
from .models import Author, Record, RecordOwner, RecordType

#: What a Proposal may continue as. Never another Proposal.
CONTINUATION_TYPES = (RecordTypeName.THESIS_RESEARCH, RecordTypeName.PROJECT)


class ContinuationRefused(Exception):
    """Why a Proposal cannot be continued, with the HTTP status that says so."""

    def __init__(self, message, status_code):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


def existing_continuation(proposal):
    """The one continuation, including a discarded child for uniqueness."""
    return Record.objects.with_deleted().filter(derived_from=proposal).first()


def continuable(record) -> bool:
    """Is `record` an accepted Proposal with no continuation yet?"""
    return (
        lifecycle.type_name_of(record) == RecordTypeName.PROPOSAL
        and record.pipeline_status == PipelineStatus.APPROVED
        and existing_continuation(record) is None
    )


def lineage_payload(record, viewer):
    """
    `{derived_from, continued_as}`: the Proposal `record` continues and the
    record continuing it, each `{id, title, record_type_name}` or None.

    A link is shown only to a viewer who may open the record it names
    (`visible_to`), so a published Thesis never discloses that a private
    Proposal exists. A deleted record is never named.
    """
    visible = Record.objects.visible_to(viewer)

    def link(queryset):
        linked = visible.filter(pk__in=queryset.values("pk")).select_related("record_type").first()
        if linked is None:
            return None
        return {
            "id": linked.pk,
            "title": linked.title,
            "record_type_name": linked.record_type.name if linked.record_type else None,
        }

    return {
        "derived_from": link(Record.objects.filter(pk=record.derived_from_id)),
        "continued_as": link(Record.objects.filter(derived_from=record)),
    }


def continue_proposal(proposal, user, record_type: RecordType) -> Record:
    """
    Make `proposal`'s continuation: a `draft` of `record_type` carrying its
    title, abstract, classification, PSCED, Adviser, owners and authors, all
    editable afterwards. The manuscript is not copied: a Proposal's is not the
    full paper.

    The Proposal's row is locked first, so two requests at once are taken one
    after the other and the second finds the first's child. The constraint on
    `derived_from` is the backstop if anything ever writes around this.
    """
    if not is_record_owner(user, proposal):
        raise ContinuationRefused("Only an owner of this proposal may continue it.", 403)
    if record_type.name not in CONTINUATION_TYPES:
        raise ContinuationRefused("A proposal continues as a Thesis / Research or a Project.", 400)

    try:
        with transaction.atomic():
            locked = Record.objects.select_for_update().get(pk=proposal.pk)
            if not is_record_owner(user, locked):
                raise ContinuationRefused("Only an owner of this proposal may continue it.", 403)
            if lifecycle.type_name_of(locked) != RecordTypeName.PROPOSAL:
                raise ContinuationRefused("Only a proposal can be continued.", 400)
            if locked.pipeline_status != PipelineStatus.APPROVED:
                raise ContinuationRefused(
                    "A proposal can be continued only once its Adviser has accepted it.", 400,
                )
            if existing_continuation(locked) is not None:
                raise ContinuationRefused("This proposal has already been continued.", 409)
            return _create_child(locked, user, record_type)
    except IntegrityError as exc:
        if getattr(getattr(exc.__cause__, "diag", None), "constraint_name", None) != "record_one_continuation":
            raise
        raise ContinuationRefused("This proposal has already been continued.", 409) from exc


def _create_child(proposal, user, record_type):
    child = Record.objects.create(
        title=proposal.title,
        abstract=proposal.abstract,
        keywords=list(proposal.keywords),
        classification=proposal.classification,
        psced=proposal.psced,
        adviser=proposal.adviser,
        record_type=record_type,
        added_by=user,
        pipeline_status=lifecycle.INITIAL_STATUS,
        derived_from=proposal,
    )
    RecordOwner.objects.bulk_create([
        RecordOwner(record=child, user_id=owner.user_id, is_primary=owner.is_primary)
        for owner in proposal.owners.all()
    ])
    Author.objects.bulk_create([
        Author(record=child, name=author.name, role_id=author.role_id)
        for author in proposal.authors.order_by("pk")
    ])
    return child
