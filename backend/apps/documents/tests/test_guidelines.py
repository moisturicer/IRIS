"""
Guidelines (ADR-063 decision 7, IR-974): what each record type needs, for anyone signed in.

Who may call the route is the access matrix's (`apps/tests/test_access_matrix.py`).
These pin what it returns: every record type in order, each with its description,
the fixed Manuscript row and the requirements RDCO lists on Setup, in RDCO's order.
A hidden requirement and a slot made for one paper's document request never show,
and nothing about Setup's bookkeeping does. It only reads.
"""

from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from apps.accounts.models import Role, User
from apps.documents.models import UploadSlot
from apps.records.models import Record, RecordType
from core.enums import RecordTypeName

URL = "/api/v1/documents/guidelines/"


class GuidelinesTests(APITestCase):
    def setUp(self):
        self.student = User.objects.create_user(
            email="guidelines-student@cit.edu", password="TestPass123!", is_verified=True,
            first_name="Gina", last_name="Student", role=Role.objects.get_or_create(name="Student")[0],
        )
        self.thesis = RecordType.objects.get(name=RecordTypeName.THESIS_RESEARCH)
        self.thesis.description = "Needs an approved Proposal first.\nSee https://cit.edu/forms"
        self.thesis.manuscript_description = "The full thesis, as one PDF."
        self.thesis.manuscript_template_name = "thesis-format.docx"
        self.thesis.save()
        UploadSlot.objects.filter(record_type=self.thesis).delete()
        self.second = UploadSlot.objects.create(
            name="Release Form", record_type=self.thesis, is_required=True,
            description="Signed by every author.", position=2, template_name="release.pdf",
        )
        self.first = UploadSlot.objects.create(
            name="Community Extension", record_type=self.thesis, is_required=False, position=1,
        )
        UploadSlot.objects.create(
            name="Old form", record_type=self.thesis, position=3, hidden_at=timezone.now(),
        )
        paper = Record.objects.create(title="One paper", record_type=self.thesis, added_by=self.student)
        UploadSlot.objects.create(name="Signed letter", record_type=self.thesis, record=paper, position=4)
        self.client.force_authenticate(self.student)

    def _guidelines(self):
        response = self.client.get(URL)
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        return response.data

    def test_every_record_type_shows_in_order(self):
        """The three types ADR-063 decision 2 names, in the order the reference migration created them."""
        names = [rt["name"] for rt in self._guidelines()]
        self.assertEqual(names, [RecordTypeName.PROPOSAL, RecordTypeName.THESIS_RESEARCH, RecordTypeName.PROJECT])

    def test_a_type_shows_its_description_and_manuscript_first(self):
        thesis = next(rt for rt in self._guidelines() if rt["id"] == self.thesis.pk)
        self.assertEqual(thesis["description"], "Needs an approved Proposal first.\nSee https://cit.edu/forms")
        self.assertEqual(thesis["manuscript"], {
            "description": "The full thesis, as one PDF.",
            "template_name": "thesis-format.docx",
        })

    def test_only_listed_requirements_show_in_rdcos_order(self):
        thesis = next(rt for rt in self._guidelines() if rt["id"] == self.thesis.pk)
        self.assertEqual(thesis["requirements"], [
            {"id": self.first.pk, "name": "Community Extension", "is_required": False,
             "description": "", "template_name": ""},
            {"id": self.second.pk, "name": "Release Form", "is_required": True,
             "description": "Signed by every author.", "template_name": "release.pdf"},
        ])

    def test_it_only_reads(self):
        for method in ("post", "put", "patch", "delete"):
            with self.subTest(method=method):
                response = getattr(self.client, method)(URL, {}, format="json")
                self.assertEqual(response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)
