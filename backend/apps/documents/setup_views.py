"""
RDCO's Setup API, and Template downloads (ADR-063, IR-971).

Setup routes are RDCO-only: `IsRDCO` refuses every other role before any
lookup, so nobody else learns whether a requirement exists. A Template
downloads for anyone signed in (Guidelines is signed-in only, decision 7), only
for a listed requirement, and always as an attachment (decision 8). Downloads
are not audited (decision 11).
"""

from __future__ import annotations

from rest_framework import status
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from core.permissions import IsRDCO

from . import setup
from .template_files import template_response

def _body(request) -> dict:
    """The request's fields as one value each, whether sent as JSON or a form."""
    data = request.data
    return data.dict() if hasattr(data, "dict") else dict(data)


def _missing(what: str) -> Response:
    return Response({"detail": f"{what} not found."}, status=status.HTTP_404_NOT_FOUND)


def _refused(error: setup.SetupError) -> Response:
    return Response({"detail": str(error)}, status=status.HTTP_400_BAD_REQUEST)


def _record_type(pk):
    from apps.records.models import RecordType

    try:
        return RecordType.objects.get(pk=pk)
    except (RecordType.DoesNotExist, ValueError, TypeError):
        return None


def requirement_payload(slot, in_use: bool | None = None) -> dict:
    if in_use is None:
        in_use = slot.uploads.exists() or slot.request_items.exists()
    return {
        "id": slot.pk,
        "name": slot.name,
        "is_required": slot.is_required,
        "description": slot.description,
        "position": slot.position,
        "template_name": slot.template_name,
        # Removing a requirement in use hides it and keeps its files (decision 5).
        "in_use": in_use,
    }


def record_type_payload(record_type) -> dict:
    from django.db.models import Exists, OuterRef

    from apps.documents.models import DocumentRequestItem, RecordUpload

    slots = setup.listed_slots(record_type.pk).annotate(
        has_uploads=Exists(RecordUpload.objects.filter(slot=OuterRef("pk"))),
        has_requests=Exists(DocumentRequestItem.objects.filter(slot=OuterRef("pk"))),
    )
    return {
        "id": record_type.pk,
        "name": record_type.name,
        "description": record_type.description,
        # The fixed first row (decision 4): always Required, never removable.
        "manuscript": {
            "description": record_type.manuscript_description,
            "template_name": record_type.manuscript_template_name,
        },
        "requirements": [
            requirement_payload(slot, in_use=slot.has_uploads or slot.has_requests) for slot in slots
        ],
    }


class SetupRecordTypeListView(APIView):
    """GET /documents/setup/record-types/ -- every record type with its Requirements."""

    permission_classes = [IsAuthenticated, IsRDCO]

    def get(self, request):
        from apps.records.models import RecordType

        return Response([record_type_payload(rt) for rt in RecordType.objects.order_by("pk")])


class SetupRecordTypeView(APIView):
    """PATCH /documents/setup/record-types/<id>/ -- `description`, `manuscript_description`."""

    permission_classes = [IsAuthenticated, IsRDCO]

    def patch(self, request, pk):
        record_type = _record_type(pk)
        if record_type is None:
            return _missing("Record type")
        try:
            record_type = setup.describe_record_type(record_type, request.user, _body(request))
        except setup.SetupError as error:
            return _refused(error)
        return Response(record_type_payload(record_type))


class SetupRequirementCreateView(APIView):
    """POST /documents/setup/record-types/<id>/requirements/ -- add a Requirement."""

    permission_classes = [IsAuthenticated, IsRDCO]

    def post(self, request, pk):
        record_type = _record_type(pk)
        if record_type is None:
            return _missing("Record type")
        try:
            slot = setup.add_requirement(
                record_type, request.user,
                name=request.data.get("name"),
                is_required=request.data.get("is_required"),
                description=request.data.get("description", ""),
            )
        except setup.SetupError as error:
            return _refused(error)
        return Response(requirement_payload(slot, in_use=False), status=status.HTTP_201_CREATED)


class SetupRequirementOrderView(APIView):
    """PUT /documents/setup/record-types/<id>/requirements/order/ -- `{"order": [ids]}`."""

    permission_classes = [IsAuthenticated, IsRDCO]

    def put(self, request, pk):
        record_type = _record_type(pk)
        if record_type is None:
            return _missing("Record type")
        order = request.data.get("order")
        if not isinstance(order, list):
            return Response({"detail": "Give the requirements' ids in their new order."},
                            status=status.HTTP_400_BAD_REQUEST)
        try:
            setup.reorder_requirements(record_type, request.user, order)
        except setup.SetupError as error:
            return _refused(error)
        return Response(record_type_payload(record_type))


class SetupRequirementView(APIView):
    """PATCH or DELETE /documents/setup/requirements/<id>/."""

    permission_classes = [IsAuthenticated, IsRDCO]

    def patch(self, request, pk):
        slot = setup.requirement(pk)
        if slot is None:
            return _missing("Requirement")
        try:
            slot = setup.edit_requirement(slot, request.user, _body(request))
        except setup.SetupError as error:
            return _refused(error)
        return Response(requirement_payload(slot))

    def delete(self, request, pk):
        slot = setup.requirement(pk)
        if slot is None:
            return _missing("Requirement")
        removal = setup.remove_requirement(slot, request.user)
        return Response({"outcome": removal.outcome.value})


class SetupRequirementTemplateView(APIView):
    """PUT (multipart `file`) or DELETE /documents/setup/requirements/<id>/template/."""

    permission_classes = [IsAuthenticated, IsRDCO]
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def put(self, request, pk):
        slot = setup.requirement(pk)
        if slot is None:
            return _missing("Requirement")
        try:
            slot = setup.set_requirement_template(slot, request.user, request.FILES.get("file"))
        except setup.SetupError as error:
            return _refused(error)
        return Response(requirement_payload(slot))

    def delete(self, request, pk):
        slot = setup.requirement(pk)
        if slot is None:
            return _missing("Requirement")
        setup.remove_requirement_template(slot, request.user)
        return Response(status=status.HTTP_204_NO_CONTENT)


class SetupManuscriptTemplateView(APIView):
    """PUT (multipart `file`) or DELETE /documents/setup/record-types/<id>/manuscript-template/."""

    permission_classes = [IsAuthenticated, IsRDCO]
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def put(self, request, pk):
        record_type = _record_type(pk)
        if record_type is None:
            return _missing("Record type")
        try:
            record_type = setup.set_manuscript_template(record_type, request.user, request.FILES.get("file"))
        except setup.SetupError as error:
            return _refused(error)
        return Response(record_type_payload(record_type))

    def delete(self, request, pk):
        record_type = _record_type(pk)
        if record_type is None:
            return _missing("Record type")
        setup.remove_manuscript_template(record_type, request.user)
        return Response(status=status.HTTP_204_NO_CONTENT)


class RequirementTemplateDownloadView(APIView):
    """GET /documents/slots/<id>/template/ -- a listed Requirement's Template, as a download."""

    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        slot = setup.requirement(pk)
        if slot is None or not slot.template:
            return _missing("Template")
        return template_response(slot.template, slot.template_name)


class ManuscriptTemplateDownloadView(APIView):
    """GET /documents/record-types/<id>/manuscript-template/ -- the Manuscript's Template."""

    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        record_type = _record_type(pk)
        if record_type is None or not record_type.manuscript_template:
            return _missing("Template")
        return template_response(record_type.manuscript_template, record_type.manuscript_template_name)
