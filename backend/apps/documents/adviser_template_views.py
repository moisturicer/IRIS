"""
My Templates API, and the shown Advisers' Templates (ADR-063 decision 8, IR-975).

`my-templates/` routes are the Adviser's own: `IsAdviser` refuses every other
role before any lookup, and each Template is looked up among the caller's own,
so another Adviser's (or anyone's, to RDCO) is a 404 identical to a missing one.
`adviser-templates/` is for anyone signed in and lists only what
`shown_templates` shows; a hidden Template's download is the same 404.
Downloads are always attachments and are not audited (decision 11).
"""

from __future__ import annotations

from rest_framework import status
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from core.permissions import IsAdviser

from . import adviser_templates as templates
from .template_files import template_response


def _missing() -> Response:
    return Response({"detail": "Template not found."}, status=status.HTTP_404_NOT_FOUND)


def _refused(error: templates.TemplateError) -> Response:
    return Response({"detail": str(error)}, status=status.HTTP_400_BAD_REQUEST)


def _fields(request) -> dict:
    """The text fields sent, as one value each, whether JSON or a form (the file is apart)."""
    data = request.data
    fields = data.dict() if hasattr(data, "dict") else dict(data)
    fields.pop("file", None)
    return fields


def template_payload(template) -> dict:
    return {
        "id": template.pk,
        "title": template.title,
        "description": template.description,
        "file_name": template.file_name,
        "position": template.position,
        "updated_at": template.updated_at,
    }


def shown_payload(template) -> dict:
    owner = template.owner
    return {
        **template_payload(template),
        "shared_by": {"id": owner.pk, "name": owner.get_full_name()},
    }


class MyTemplateListView(APIView):
    """GET (the Adviser's own) or POST (multipart `title`, `description`, `file`) /documents/my-templates/."""

    permission_classes = [IsAuthenticated, IsAdviser]
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def get(self, request):
        return Response([template_payload(t) for t in templates.my_templates(request.user)])

    def post(self, request):
        fields = _fields(request)
        try:
            template = templates.add_template(
                request.user, title=fields.get("title"), description=fields.get("description"),
                file=request.FILES.get("file"),
            )
        except templates.TemplateError as error:
            return _refused(error)
        return Response(template_payload(template), status=status.HTTP_201_CREATED)


class MyTemplateOrderView(APIView):
    """PUT /documents/my-templates/order/ with `{"order": [ids]}`."""

    permission_classes = [IsAuthenticated, IsAdviser]

    def put(self, request):
        try:
            order = templates.reorder_templates(request.user, request.data.get("order") or [])
        except templates.TemplateError as error:
            return _refused(error)
        return Response({"order": order})


class MyTemplateView(APIView):
    """PATCH (`title`, `description`, optional multipart `file`) or DELETE /documents/my-templates/<id>/."""

    permission_classes = [IsAuthenticated, IsAdviser]
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def patch(self, request, pk):
        template = templates.own_template(request.user, pk)
        if template is None:
            return _missing()
        try:
            template = templates.edit_template(
                template, request.user, _fields(request), file=request.FILES.get("file"),
            )
        except templates.TemplateError as error:
            return _refused(error)
        except templates.TemplateGone:
            return _missing()
        return Response(template_payload(template))

    def delete(self, request, pk):
        template = templates.own_template(request.user, pk)
        if template is None:
            return _missing()
        try:
            templates.remove_template(template, request.user)
        except templates.TemplateGone:
            return _missing()
        return Response(status=status.HTTP_204_NO_CONTENT)


class MyTemplateDownloadView(APIView):
    """
    GET /documents/my-templates/<id>/file/ -- the Adviser's own file, as a download,
    whether or not it shows to others yet (an unverified account shows nothing).
    """

    permission_classes = [IsAuthenticated, IsAdviser]

    def get(self, request, pk):
        template = templates.own_template(request.user, pk)
        if template is None:
            return _missing()
        return template_response(template.file, template.file_name)


class ShownAdviserTemplateListView(APIView):
    """
    GET /documents/adviser-templates/ -- every shown Template, by Adviser.
    Guidelines (IR-974) searches it by Adviser in the browser, so there is no filter here.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response([shown_payload(t) for t in templates.shown_templates()])


class AdviserTemplateDownloadView(APIView):
    """GET /documents/adviser-templates/<id>/file/ -- a shown Template, as a download."""

    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        try:
            template = templates.shown_templates().get(pk=pk)
        except (templates.AdviserTemplate.DoesNotExist, ValueError, TypeError):
            return _missing()
        return template_response(template.file, template.file_name)
