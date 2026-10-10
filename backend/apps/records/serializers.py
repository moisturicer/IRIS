from django.utils import timezone
from rest_framework import serializers
from core.enums import ReviewDecision

from apps.documents.validators import pdf_upload_problem
from apps.reviews.clearance_state import clearance_payload, resubmission_payload

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


class RecordListSerializer(serializers.ModelSerializer):
    """Lightweight serializer for list views and DataTable."""
    classification_name = serializers.CharField(source="classification.name", read_only=True)
    record_type_name    = serializers.CharField(source="record_type.name", read_only=True)
    authors             = AuthorSerializer(many=True, read_only=True)
    # Annotated by RecordViewSet.get_queryset; 0 when the queryset omits it.
    file_count          = serializers.IntegerField(read_only=True, default=0)

    class Meta:
        model  = Record
        fields = [
            "id", "title", "abstract", "year_accomplished", "classification_name",
            "record_type_name", "pipeline_status", "is_ip", "ip_type",
            "for_commercialization", "community_extension",
            "access_count", "file_count", "created_at", "authors",
        ]


class RecordDetailSerializer(serializers.ModelSerializer):
    """Full record detail including all related objects."""
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
    # The record's versions, for the header's version picker (IR-416).
    # Participants only, like `reviews`.
    versions             = serializers.SerializerMethodField()
    # The stored manuscript is the owner's upload for a version not yet
    # submitted (IR-273). True for an owner only; everyone else is served the
    # latest version's manuscript meanwhile, so it is never theirs to label.
    manuscript_unsubmitted = serializers.SerializerMethodField()

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

    def get_my_seats(self, obj):
        from apps.reviews.seats import my_seats

        return my_seats(obj, self._viewer())

    def get_is_participant(self, obj):
        from core.permissions import is_record_participant

        return is_record_participant(self._viewer(), obj)

    def get_routing(self, obj):
        from apps.reviews.routing import routing_flags

        return routing_flags(obj, self._viewer())

    def get_office_review(self, obj):
        from apps.reviews.office_review import office_review_flags

        return office_review_flags(obj, self._viewer())

    def get_revision(self, obj):
        from apps.reviews.revisions import revision_flags

        return revision_flags(obj, self._viewer(), readable=self._readable(obj))

    def get_decision(self, obj):
        from apps.reviews.decisions import decision_flags

        return decision_flags(obj, self._viewer())

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
        return [
            clearance_payload(c, last_resubmitted_at=obj.last_resubmitted_at, readable=readable)
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
            "classification_name", "record_type_name", "file_count",
            "adviser", "added_by", "is_ip", "ip_type",
            "for_commercialization", "community_extension",
            "requires_ethics_review", "requested_itso", "requested_ierc", "requested_ktto",
            "access_count", "pipeline_status", "stage_label", "is_deleted",
            "workflow_state", "workflow_state_label", "current_holders",
            "can_request_document", "my_seats", "is_participant", "routing",
            "office_review", "revision", "decision",
            "dpa_accepted", "dpa_accepted_at",
            "created_at", "updated_at",
            "owners", "authors", "reviews", "clearances", "resubmission", "files",
            "versions", "manuscript_unsubmitted",
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
            "authors",
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

    def _sync_authors(self, record, authors_data: list[str]):
        """Replace all Author rows for a record with the provided name list."""
        from .models import Author
        record.authors.all().delete()
        Author.objects.bulk_create(
            [Author(record=record, name=name.strip()) for name in authors_data if name.strip()]
        )

    def create(self, validated_data):
        authors_data = validated_data.pop("authors", [])
        record = super().create(validated_data)
        if authors_data:
            self._sync_authors(record, authors_data)
        return record

    def update(self, instance, validated_data):
        authors_data = validated_data.pop("authors", None)
        from core.permissions import is_record_owner

        editor = getattr(self.context.get("request"), "user", None)
        if is_record_owner(editor, instance) and self._details_changed(instance, validated_data, authors_data):
            # What a new version answers a revision request with, when no file
            # changed (IR-273). Only an owner's real change: the revision is
            # theirs, and saving the same details again answers nothing.
            validated_data["details_edited_at"] = timezone.now()
        record = super().update(instance, validated_data)
        if authors_data is not None:           # only replace when field was explicitly sent
            self._sync_authors(record, authors_data)
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
