from django.utils import timezone
from rest_framework import serializers
from core.enums import PipelineStatus, ReviewDecision

from apps.documents.validators import pdf_upload_problem
from apps.reviews.clearance_state import clearance_payload, record_versions, resubmission_payload

from .models import (
    Record, RecordOwner, Author, DownloadRequest, DeleteRequest,
    Classification, PSCEDClassification, RecordType,
)


class AuthorSerializer(serializers.ModelSerializer):
    class Meta:
        model  = Author
        fields = ["id", "name", "role"]


class RecordOwnerSerializer(serializers.ModelSerializer):
    email      = serializers.CharField(source="user.email", read_only=True)
    full_name  = serializers.CharField(source="user.get_full_name", read_only=True)

    class Meta:
        model  = RecordOwner
        fields = ["id", "user", "email", "full_name", "is_primary"]


def ai_hook(record):
    """The Overview's one-sentence hook for a catalogue card (IR-604), or None.

    Lazy import: `apps.ai` imports `Record`.
    """
    from apps.ai.overview.service import hook_for

    return hook_for(record)


class RecordListSerializer(serializers.ModelSerializer):
    """Lightweight serializer for list views and DataTable."""
    classification_name = serializers.CharField(source="classification.name", read_only=True)
    record_type_name    = serializers.CharField(source="record_type.name", read_only=True)
    authors             = AuthorSerializer(many=True, read_only=True)
    # Annotated by RecordViewSet.get_queryset; 0 when the queryset omits it.
    file_count          = serializers.IntegerField(read_only=True, default=0)
    has_manuscript      = serializers.SerializerMethodField()

    def get_has_manuscript(self, obj):
        return bool(obj.abstract_file or getattr(obj, "file_count", 0))

    ai_hook             = serializers.SerializerMethodField()

    def get_ai_hook(self, obj):
        return ai_hook(obj)

    class Meta:
        model  = Record
        fields = [
            "id", "title", "abstract", "year_accomplished", "classification_name",
            "record_type_name", "pipeline_status", "is_ip", "ip_type",
            "for_commercialization", "community_extension",
            "access_count", "file_count", "has_manuscript", "created_at", "authors", "ai_hook",
        ]


class MyResearchSerializer(serializers.ModelSerializer):
    """
    `/records/mine/`: what a *My research* card shows, and nothing else
    (IR-410; spec §4.9 as amended 2026-10-11). The status line is
    `workflow_state_label`, the next step comes from `workflow_state`, and My
    Library groups the list by `holders`, so the client derives no stage.

    `context["workflow_facts"]` holds every listed record's facts, worked out
    in one pass by `tracker.workflow_facts`, so the list's query count does
    not grow with its length. Record detail's viewer-dependent blocks stay
    on detail.
    """
    can_continue         = serializers.SerializerMethodField()
    record_type_name     = serializers.CharField(source="record_type.name", read_only=True)

    def get_can_continue(self, obj):
        from core.enums import PipelineStatus, RecordTypeName

        return (obj.record_type is not None
                and obj.record_type.name == RecordTypeName.PROPOSAL
                and obj.pipeline_status == PipelineStatus.APPROVED
                and not obj.has_continuation)
    authors              = AuthorSerializer(many=True, read_only=True)
    adviser_name         = serializers.SerializerMethodField()
    workflow_state       = serializers.SerializerMethodField()
    workflow_state_label = serializers.SerializerMethodField()
    # Who has the record now: `[{party, label}]`, in tracker order.
    holders              = serializers.SerializerMethodField()
    # `[{office, label, preserved}]`: each office that has cleared it, and
    # whether that clearance was kept through a resubmission (ADR-003).
    cleared_offices      = serializers.SerializerMethodField()
    # The owner's status line and what waits on them (IR-625). Every row
    # here is the caller's own record.
    submitter_status     = serializers.SerializerMethodField()

    def _facts(self, obj):
        return self.context["workflow_facts"][obj.pk]

    def get_adviser_name(self, obj):
        if obj.adviser:
            return obj.adviser.get_full_name() or obj.adviser.email
        return None

    def get_workflow_state(self, obj):
        return self._facts(obj)["workflow_state"]

    def get_workflow_state_label(self, obj):
        from apps.reviews.tracker import record_state_label

        return record_state_label(obj, self.get_workflow_state(obj))

    def get_holders(self, obj):
        return self._facts(obj)["holders"]

    def get_cleared_offices(self, obj):
        return self._facts(obj)["cleared_offices"]

    def get_submitter_status(self, obj):
        from apps.reviews.submitter_status import submitter_status

        facts = self._facts(obj)
        return submitter_status(
            record=obj, workflow_state=facts["workflow_state"],
            holders=[h["party"] for h in facts["holders"]],
            revision_parties=facts["revision_parties"],
            document_parties=facts["document_parties"],
        )

    class Meta:
        model  = Record
        fields = [
            "id", "title", "record_type_name", "authors", "adviser_name",
            "pipeline_status", "workflow_state", "workflow_state_label",
            "holders", "cleared_offices", "submitter_status", "created_at", "updated_at", "can_continue",
        ]
        read_only_fields = fields


class RecordDetailSerializer(serializers.ModelSerializer):
    """Full record detail including all related objects."""
    keywords = serializers.ListField(child=serializers.CharField(), read_only=True)
    owners         = RecordOwnerSerializer(many=True, read_only=True)
    authors        = AuthorSerializer(many=True, read_only=True)
    classification = serializers.StringRelatedField()
    psced          = serializers.StringRelatedField()
    record_type    = serializers.StringRelatedField()
    # Mirrored from RecordListSerializer so the detail payload is a strict
    # superset of the list payload — the frontend types RecordDetail as an
    # extension of RecordListItem and reads these on the paper view.
    classification_name = serializers.CharField(source="classification.name", read_only=True)
    record_type_name    = serializers.CharField(source="record_type.name", read_only=True)
    file_count          = serializers.SerializerMethodField()
    has_manuscript      = serializers.SerializerMethodField()

    def get_has_manuscript(self, obj):
        from .download_service import has_record_download_file

        return has_record_download_file(obj)

    ai_hook             = serializers.SerializerMethodField()
    # Paper View's byline credits the adviser by name (IR-472). It rides on
    # the record's own visibility: whoever may read the record may read this.
    adviser_name   = serializers.SerializerMethodField()
    reviews        = serializers.SerializerMethodField()
    clearances     = serializers.SerializerMethodField()
    resubmission   = serializers.SerializerMethodField()
    stage_label    = serializers.CharField(source="get_pipeline_status_display", read_only=True)
    files          = serializers.SerializerMethodField()
    # Read as the manuscript endpoint, not the stored `/media/` path (IR-334).
    abstract_file  = serializers.SerializerMethodField()
    # Derived from the routing tables, never stored (ADR-021 §4, IR-258).
    workflow_state       = serializers.SerializerMethodField()
    workflow_state_label = serializers.SerializerMethodField()
    current_holders      = serializers.SerializerMethodField()
    # The parties this viewer may ask the owner for documents as (IR-262).
    can_request_document = serializers.SerializerMethodField()
    # The viewer's own reviewer seats here, and whether they take part in the
    # review at all -- an owner, or anyone who has ever held a seat
    # (ADR-032 §4, §10; IR-415).
    my_seats             = serializers.SerializerMethodField()
    is_participant       = serializers.SerializerMethodField()
    # What Paper View's action bar may offer for routing (ADR-032 §4, IR-261):
    # `{accept_and_route: bool, route_as: party | null}`. A rendering hint;
    # the routing endpoints re-check both.
    routing              = serializers.SerializerMethodField()
    # What the action bar may offer an office reviewer (IR-269): `{party,
    # label, blocked, assignment}` -- the office the viewer may clear or
    # record a finding as, why not yet, and its assignment for *Add reviewer*.
    # A rendering hint; `office-review/` and `add-reviewer/` re-check it.
    office_review        = serializers.SerializerMethodField()
    # Revision requests (IR-272): `{party, label, blocked, withdrawable,
    # decision_blocked, open}` -- whether the viewer may ask for a revision
    # or withdraw their party's, why nothing can be decided now, and every
    # open request for the owner's *Action required*. A rendering hint;
    # `request-revision/` and the withdraw endpoint re-check it.
    revision             = serializers.SerializerMethodField()
    # Decisions (IR-270): `{party, outcomes, blocked, closes, token,
    # author_hints}` -- what the viewer may decide this record as, why not
    # yet, what deciding would close, and the token `decide/` checks so a
    # stale dialog never decides into a changed record. A rendering hint;
    # `decide/` re-checks it.
    decision             = serializers.SerializerMethodField()
    # What the viewer may be offered (ADR-032 §10, IR-418): `core.permissions`
    # assembles it from the blocks above. A rendering hint; every action
    # endpoint re-checks its own predicate, so the server stays authoritative.
    capabilities         = serializers.SerializerMethodField()
    # The record's versions, for the header's version picker (IR-416).
    # Participants only, like `reviews`.
    versions             = serializers.SerializerMethodField()
    # The stored manuscript is the owner's upload for a version not yet
    # submitted (IR-273). True for an owner only; everyone else is served the
    # latest version's manuscript meanwhile, so it is never theirs to label.
    manuscript_unsubmitted = serializers.SerializerMethodField()
    # The owner's status line, what waits on them, and each version's
    # history (IR-625). `None` to anyone but an owner.
    submitter_status     = serializers.SerializerMethodField()
    # `{derived_from, continued_as}`: the Proposal this continues and what
    # continues it (ADR-032 §6, IR-417), each only if the viewer may open it.
    lineage              = serializers.SerializerMethodField()

    def _workflow(self, obj):
        """
        The workflow fields, computed once per record. `can_request_document`
        depends on the viewer, so it comes from the request.
        """
        cache = self.__dict__.setdefault("_workflow_cache", {})
        if obj.pk not in cache:
            from apps.reviews.tracker import workflow_fields

            request = self.context.get("request")
            cache[obj.pk] = workflow_fields(
                obj, getattr(request, "user", None), readable=self._readable(obj),
            )
        return cache[obj.pk]

    def _readable(self, obj) -> bool:
        """
        May the viewer read this record's review content -- who reviewed it
        and what they wrote (IR-479)? Once per record; `reviews`, the
        clearances' comments and signers, and `current_holders[].opened_by`
        all follow it.
        """
        cache = self.__dict__.setdefault("_readable_cache", {})
        if obj.pk not in cache:
            from core.permissions import may_read_review

            cache[obj.pk] = may_read_review(self._viewer(), obj)
        return cache[obj.pk]

    def get_workflow_state(self, obj):
        return self._workflow(obj)["workflow_state"]

    def get_workflow_state_label(self, obj):
        return self._workflow(obj)["workflow_state_label"]

    def get_current_holders(self, obj):
        return self._workflow(obj)["current_holders"]

    def get_can_request_document(self, obj):
        return self._workflow(obj)["can_request_document"]

    def _viewer(self):
        return getattr(self.context.get("request"), "user", None)

    def _once(self, obj, name, compute):
        """
        A viewer-dependent block, computed once per record. `capabilities`
        reads the same blocks the payload carries (IR-418), and each costs
        queries, so neither field computes them a second time.
        """
        cache = self.__dict__.setdefault("_block_cache", {})
        key = (obj.pk, name)
        if key not in cache:
            cache[key] = compute()
        return cache[key]

    def get_my_seats(self, obj):
        from apps.reviews.seats import my_seats

        return self._once(obj, "my_seats", lambda: my_seats(obj, self._viewer()))

    def get_is_participant(self, obj):
        from core.permissions import is_record_participant

        return is_record_participant(self._viewer(), obj)

    def get_routing(self, obj):
        from apps.reviews.routing import routing_flags

        return self._once(obj, "routing", lambda: routing_flags(obj, self._viewer()))

    def get_office_review(self, obj):
        from apps.reviews.office_review import office_review_flags

        return self._once(obj, "office_review", lambda: office_review_flags(obj, self._viewer()))

    def get_revision(self, obj):
        from apps.reviews.revisions import revision_flags

        return self._once(
            obj, "revision",
            lambda: revision_flags(obj, self._viewer(), readable=self._readable(obj)),
        )

    def get_decision(self, obj):
        from apps.reviews.decisions import decision_flags

        return self._once(obj, "decision", lambda: decision_flags(obj, self._viewer()))

    def get_capabilities(self, obj):
        from core.permissions import record_capabilities

        return record_capabilities(
            obj, self._viewer(), workflow=self._workflow(obj),
            my_seats=self.get_my_seats(obj), routing=self.get_routing(obj),
            office_review=self.get_office_review(obj), revision=self.get_revision(obj),
            decision=self.get_decision(obj),
        )

    def get_reviews(self, obj):
        """
        Every review on the record, with its comment and reviewer. Internal
        workflow data: `None` -- not disclosed, which is not `[]` -- to a
        viewer who may not read the review (IR-479).
        """
        from apps.reviews.models import Review

        if not self._readable(obj):
            return None
        qs = (
            Review.objects
            .filter(record=obj)
            .select_related("reviewed_by", "version")
            .order_by("created_at")
        )
        return [
            {
                "id":               r.id,
                "stage":            r.stage,
                "status":           r.status,
                "comment":          r.comment,
                "reviewed_by_name": r.reviewed_by.get_full_name() if r.reviewed_by else None,
                "created_at":       r.created_at.isoformat(),
                # The version it was made against; null before IR-416.
                "version":          r.version.number if r.version else None,
            }
            for r in qs
        ]

    def get_versions(self, obj):
        """
        The record's versions, oldest first (ADR-032 §5, IR-416). Review
        material: `None` -- not disclosed, which is not `[]` -- to a viewer
        who may not read the review (IR-479).
        """
        from .versions import versions_payload

        if not self._readable(obj):
            return None
        return versions_payload(obj)

    def get_manuscript_unsubmitted(self, obj):
        from .versions import manuscript_unsubmitted

        return manuscript_unsubmitted(obj, self._viewer())

    def get_lineage(self, obj):
        from .continuation import lineage_payload

        return lineage_payload(obj, self._viewer())

    def get_submitter_status(self, obj):
        from apps.reviews.submitter_status import detail_status
        from core.permissions import is_record_owner

        if not is_record_owner(self._viewer(), obj):
            return None
        workflow = self._workflow(obj)
        return detail_status(
            obj, workflow_state=workflow["workflow_state"],
            holders=[h["party"] for h in workflow["current_holders"]],
        )

    def _ordered_clearances(self, obj):
        return list(obj.clearances.select_related("reviewed_by").order_by("office"))

    def get_clearances(self, obj):
        """
        Per-office clearance state. This is what makes clearance-aware
        resubmission visible: `preserved` is true for a clearance that survived
        a resubmission rather than being granted again.

        The rule itself lives in `apps.reviews.clearance_state` so the server is
        its only author -- `PaperViewPage` used to re-derive it in TypeScript
        against a different definition (IR-139).
        """
        readable = self._readable(obj)
        versions = record_versions(obj)
        return [
            clearance_payload(
                c, last_resubmitted_at=obj.last_resubmitted_at, readable=readable,
                versions=versions,
            )
            for c in self._ordered_clearances(obj)
        ]

    def get_resubmission(self, obj):
        """`resubmission{}` -- what happened, and which offices survived it."""
        latest_decline = (
            obj.reviews.filter(status=ReviewDecision.DECLINED).order_by("-created_at").first()
        )
        return resubmission_payload(
            obj,
            clearances=self._ordered_clearances(obj),
            latest_decline_stage=latest_decline.stage if latest_decline else None,
        )

    def get_ai_hook(self, obj):
        return ai_hook(obj)

    def get_file_count(self, obj):
        return obj.files.count()

    def get_files(self, obj):
        # `/documents/files/<id>/download/`, not `f.file.url`. The latter is a
        # `/media/` path, which nothing has served since IR-152 removed both
        # the nginx block and Django's DEBUG route -- every one of these links
        # was a 404 (IR-334).
        from apps.documents.attachments import may_remove, removable_parties

        files = list(obj.files.all().order_by("-created_at"))
        if not files:
            return []
        user = getattr(self.context.get("request"), "user", None)
        # The delete view's own rule (IR-476), asked once for the record.
        removable = removable_parties(obj, user)
        return [
            {
                "id":          f.id,
                "filename":    f.filename,
                "url":         f"/api/v1/documents/files/{f.id}/download/" if f.file else None,
                "size_bytes":  f.file.size if f.file else 0,
                "created_at":  f.created_at.isoformat(),
                "can_remove":  may_remove(f, user, removable=removable),
            }
            for f in files
        ]

    def get_adviser_name(self, obj):
        if obj.adviser:
            return obj.adviser.get_full_name() or obj.adviser.email
        return None

    def get_abstract_file(self, obj):
        """The paper, at a URL that is actually served (IR-334).

        The stored value is a `/media/` path that IR-152 left unroutable, so
        this reports the manuscript endpoint instead. Null when the record
        carries no file anywhere -- `manuscript` also falls back to the newest
        upload, so a record with only an upload still answers here.
        """
        from .download_service import has_record_download_file

        if not has_record_download_file(obj):
            return None
        return f"/api/v1/records/{obj.id}/manuscript/"

    class Meta:
        model  = Record
        fields = [
            "id", "title", "abstract", "abstract_file",
            "year_accomplished", "year_completed",
            "classification", "psced", "record_type",
            "classification_name", "record_type_name", "file_count", "has_manuscript", "ai_hook",
            "adviser", "adviser_name", "added_by", "is_ip", "ip_type",
            "for_commercialization", "community_extension",
            "requires_ethics_review", "requested_itso", "requested_ierc", "requested_ktto",
            "access_count", "pipeline_status", "stage_label", "is_deleted",
            "workflow_state", "workflow_state_label", "current_holders",
            "can_request_document", "my_seats", "is_participant", "routing",
            "office_review", "revision", "decision", "capabilities", "keywords",
            "dpa_accepted", "dpa_accepted_at",
            "created_at", "updated_at",
            "owners", "authors", "reviews", "clearances", "resubmission", "files",
            "versions", "manuscript_unsubmitted", "submitter_status", "lineage",
        ]
        # Consent is stamped by `RecordViewSet.submit` and read everywhere else
        # (IR-226). `dpa_accepted` is a model property so DRF would infer it as
        # read-only anyway; naming both here states the intent rather than
        # relying on that inference, and keeps `dpa_accepted_at` -- a real,
        # writable column -- from becoming settable if this serializer is ever
        # given a write path.
        read_only_fields = ["dpa_accepted", "dpa_accepted_at"]


class RecordWriteSerializer(serializers.ModelSerializer):
    """
    Used for create and update operations.
    `authors` is a flat list of name strings — the serializer handles creating
    and replacing Author rows so callers never touch the Author model directly.
    """
    keywords = serializers.ListField(child=serializers.CharField(max_length=100), max_length=30, required=False)
    owner_emails = serializers.ListField(child=serializers.EmailField(), max_length=30, required=False, write_only=True)
    authors = serializers.ListField(
        child=serializers.CharField(max_length=200, allow_blank=False),
        write_only=True,
        required=False,
        default=list,
        help_text="List of author name strings. On update, replaces all existing authors.",
    )

    class Meta:
        model  = Record
        fields = [
            "id",
            "title", "year_accomplished", "year_completed", "abstract",
            "classification", "psced", "record_type", "adviser",
            "is_ip", "for_commercialization", "community_extension",
            "requires_ethics_review", "requested_itso", "requested_ierc", "requested_ktto",
            "abstract_file",
            "authors", "keywords", "owner_emails",
        ]
        read_only_fields = ["id", "pipeline_status", "added_by"]

    def validate_abstract_file(self, file):
        """The manuscript is a PDF within the upload limit (IR-408).

        The same rule `SubmitDocumentView` applies to supplementary files, from
        the one module both use. Publish checks it in the browser first; this
        is the boundary.
        """
        # Once submitted, the manuscript changes only through a new version
        # (ADR-032 §5 Amendment, IR-416). Staff are not exempt, and clearing it
        # is a change too. While a revision is asked for, only an owner may
        # (IR-273).
        from .versions import may_replace_manuscript

        user = getattr(self.context.get("request"), "user", None)
        if self.instance is not None and not may_replace_manuscript(self.instance, user):
            raise serializers.ValidationError(
                "The manuscript cannot be replaced while this record is "
                f"'{self.instance.pipeline_status}'. Once a record is submitted, "
                "its manuscript changes only when a new version is submitted."
            )
        if not file:
            return file
        problem = pdf_upload_problem(file)
        if problem:
            raise serializers.ValidationError(problem)
        return file

    def validate(self, attrs):
        """
        What an owner may change (IR-507, ADR-032 §10 Amendment).

        Only an owner reaches an update (`IsRecordOwner`), and only while the
        record is a `draft` or awaits their revision (`RecordViewSet.update`).
        Once submitted, the fields in `versions.SUBMISSION_FIXED_FIELDS` stay
        as they were submitted. Sending one unchanged is not a change, so a
        form that re-sends every field still saves; changing any is one
        refusal naming each field, so a single correction clears them all.
        """
        if self.instance is None:
            return attrs
        from .versions import SUBMISSION_FIXED_FIELDS

        record = self.instance
        if record.derived_from_id and "record_type" in attrs:
            from .continuation import CONTINUATION_TYPES
            if attrs["record_type"] is None or attrs["record_type"].name not in CONTINUATION_TYPES:
                raise serializers.ValidationError({"record_type": "A continuation must remain a Thesis / Research or Project."})
        if "owner_emails" in attrs:
            from apps.accounts.models import User

            if record.pipeline_status != PipelineStatus.DRAFT:
                raise serializers.ValidationError({"owner_emails": "Owners can be changed only on a draft."})
            emails = {email.lower() for email in attrs["owner_emails"]}
            user = self.context["request"].user
            from django.db.models.functions import Lower
            owners = list(User.objects.annotate(normalized_email=Lower("email")).filter(normalized_email__in=emails, is_active=True))
            adviser = attrs.get(Record.adviser.field.name, record.adviser)
            if len(owners) != len(emails) or user.email.lower() not in emails or (adviser and adviser.email.lower() in emails):
                raise serializers.ValidationError({"owner_emails": "Use existing active accounts, include yourself, and exclude the Adviser."})
            attrs["owner_emails"] = owners
        if record.pipeline_status != PipelineStatus.DRAFT:
            changed = [
                field for field in SUBMISSION_FIXED_FIELDS
                if field in attrs and attrs[field] != getattr(record, field)
            ]
            if changed:
                raise serializers.ValidationError({
                    field: "This was fixed when the record was submitted and cannot be changed now."
                    for field in changed
                })
        return attrs

    def _sync_authors(self, record, authors_data: list[str]):
        """Replace all Author rows for a record with the provided name list."""
        from .models import Author
        record.authors.all().delete()
        Author.objects.bulk_create(
            [Author(record=record, name=name.strip()) for name in authors_data if name.strip()]
        )

    def create(self, validated_data):
        if "owner_emails" in validated_data:
            raise serializers.ValidationError({"owner_emails": "Save the draft before editing its owners."})
        authors_data = validated_data.pop("authors", [])
        record = super().create(validated_data)
        if authors_data:
            self._sync_authors(record, authors_data)
        return record

    def update(self, instance, validated_data):
        from django.db import transaction
        from .models import RecordOwner

        owners = validated_data.pop("owner_emails", None)
        authors_data = validated_data.pop("authors", None)
        if self._details_changed(instance, validated_data, authors_data):
            # What a new version answers a revision request with, when no file
            # changed (IR-273). Only a real change: saving the same details
            # again answers nothing. Only an owner edits at all (IR-507), so
            # every change stamped here is the owner's own revision.
            validated_data["details_edited_at"] = timezone.now()
        with transaction.atomic():
            record = super().update(instance, validated_data)
            if authors_data is not None:
                self._sync_authors(record, authors_data)
            if owners is not None:
                primary = record.owners.filter(is_primary=True, user__in=owners).first()
                primary_id = primary.user_id if primary else self.context["request"].user.pk
                record.owners.all().delete()
                RecordOwner.objects.bulk_create([
                    RecordOwner(record=record, user=user, is_primary=user.pk == primary_id)
                    for user in owners
                ])
        return record

    @staticmethod
    def _details_changed(instance, validated_data, authors_data) -> bool:
        """Does this update change a detail? The manuscript is not one (IR-273)."""
        for field, value in validated_data.items():
            if field == "abstract_file":
                continue
            if getattr(instance, field) != value:
                return True
        if authors_data is None:
            return False
        sent = [name.strip() for name in authors_data if name.strip()]
        return sent != list(instance.authors.order_by("pk").values_list("name", flat=True))


class VisibleRecordField(serializers.PrimaryKeyRelatedField):
    """
    A record id, resolved only among the records the requester may read
    (`Record.objects.visible_to`, IR-153). An id outside that set fails exactly
    as an id no record has -- same code, same message -- so a request endpoint
    cannot be used to learn that a private record exists (IR-316).
    """
    def get_queryset(self):
        request = self.context.get("request")
        return Record.objects.visible_to(getattr(request, "user", None))


class DownloadRequestSerializer(serializers.ModelSerializer):
    record               = VisibleRecordField()
    record_title         = serializers.CharField(source="record.title",                    read_only=True)
    requested_by_name    = serializers.SerializerMethodField()
    requested_by_email   = serializers.CharField(source="requested_by.email",              read_only=True)

    class Meta:
        model  = DownloadRequest
        fields = [
            "id", "record", "record_title",
            "requested_by", "requested_by_name", "requested_by_email",
            "status", "reviewed_by", "reviewed_at", "created_at",
        ]
        # A request is created pending; only the review actions move it.
        read_only_fields = ["requested_by", "status", "reviewed_by", "reviewed_at"]

    def get_requested_by_name(self, obj):
        if obj.requested_by:
            return obj.requested_by.get_full_name() or obj.requested_by.email
        return None


class DeleteRequestSerializer(serializers.ModelSerializer):
    """Output only: the queue is read and decided, never written to (IR-496)."""
    record_title         = serializers.CharField(source="record.title",                    read_only=True)
    requested_by_name    = serializers.SerializerMethodField()
    requested_by_email   = serializers.CharField(source="requested_by.email",              read_only=True)

    class Meta:
        model  = DeleteRequest
        fields = [
            "id", "record", "record_title",
            "requested_by", "requested_by_name", "requested_by_email",
            "reason", "status", "reviewed_by", "reviewed_at", "created_at",
        ]
        read_only_fields = fields

    def get_requested_by_name(self, obj):
        if obj.requested_by:
            return obj.requested_by.get_full_name() or obj.requested_by.email
        return None


# ---- Reference data serializers -----------------------------------------

class ClassificationSerializer(serializers.ModelSerializer):
    class Meta:
        model  = Classification
        fields = ["id", "name"]


class PSCEDSerializer(serializers.ModelSerializer):
    class Meta:
        model  = PSCEDClassification
        fields = ["id", "name"]


class RecordTypeSerializer(serializers.ModelSerializer):
    class Meta:
        model  = RecordType
        fields = ["id", "name"]
