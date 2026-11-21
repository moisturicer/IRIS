"""
RDCO's Setup: Requirements, Templates and record type descriptions (ADR-063, IR-971).

Who may call each route is the access matrix's (`apps/tests/test_access_matrix.py`):
Setup is RDCO's alone, Template downloads anyone signed in. These pin what the
routes do: that a change shows at once wherever slots show, that the Manuscript
can't be removed or made Optional, that removing never loses a file, which files
a Template may be, that it always downloads, and that every change is audited.
"""

import shutil
import tempfile

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from rest_framework import status
from rest_framework.test import APITestCase

from apps.accounts.models import Role, User
from apps.audit.models import AuditEvent
from apps.documents.models import RecordUpload, UploadSlot
from apps.documents.template_files import MAX_TEMPLATE_BYTES, template_problem
from apps.records.models import Record, RecordOwner, RecordType
from core.enums import RecordTypeName

BASE = "/api/v1/documents"
PDF = b"%PDF-1.4\n% a form\n"
DOCX = b"PK\x03\x04" + b"\x00" * 26


def upload(name="form.pdf", content=PDF, content_type="application/pdf"):
    return SimpleUploadedFile(name, content, content_type=content_type)


class SetupBase(APITestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._media_root = tempfile.mkdtemp(prefix="iris-test-media-")
        cls._media_override = override_settings(MEDIA_ROOT=cls._media_root)
        cls._media_override.enable()

    @classmethod
    def tearDownClass(cls):
        cls._media_override.disable()
        shutil.rmtree(cls._media_root, ignore_errors=True)
        super().tearDownClass()

    def setUp(self):
        self.rdco = self._user("setup-rdco@cit.edu", "RDCO")
        self.student = self._user("setup-student@cit.edu", "Student")
        self.thesis = RecordType.objects.get(name=RecordTypeName.THESIS_RESEARCH)
        self.client.force_authenticate(self.rdco)

    def _user(self, email, role):
        return User.objects.create_user(
            email=email, password="TestPass123!", is_verified=True,
            first_name="Setup", last_name=role.title(),
            role=Role.objects.get_or_create(name=role)[0],
        )

    def _setup(self):
        response = self.client.get(f"{BASE}/setup/record-types/")
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        return {rt["name"]: rt for rt in response.data}

    def _listed_names(self, record_type=None):
        """What Publish and Paper View list for a record type: `slots/`."""
        rt = record_type or self.thesis
        return [slot["name"] for slot in self._listed(rt)]

    def _listed(self, record_type=None):
        rt = record_type or self.thesis
        return self.client.get(f"{BASE}/slots/", {"record_type": rt.pk}).data["results"]

    def _add(self, name="Adviser's Endorsement", is_required=False, description="", record_type=None):
        rt = record_type or self.thesis
        return self.client.post(
            f"{BASE}/setup/record-types/{rt.pk}/requirements/",
            {"name": name, "is_required": is_required, "description": description}, format="json",
        )

    def _events(self, event_type):
        return AuditEvent.objects.filter(event_type=event_type).order_by("pk")

    def _paper(self):
        record = Record.objects.create(title="A paper with files", record_type=self.thesis,
                                       added_by=self.student)
        RecordOwner.objects.create(record=record, user=self.student, is_primary=True)
        return record


class RequirementTests(SetupBase):
    def test_setup_lists_each_record_type_with_the_manuscript_first(self):
        setup = self._setup()

        self.assertEqual(set(setup), {"Proposal", "Thesis / Research", "Project"})
        thesis = setup["Thesis / Research"]
        self.assertEqual(thesis["manuscript"], {"description": "", "template_name": ""})
        self.assertNotIn("Manuscript", [r["name"] for r in thesis["requirements"]])
        self.assertEqual(
            [r["position"] for r in thesis["requirements"]],
            sorted(r["position"] for r in thesis["requirements"]),
        )

    def test_an_added_requirement_shows_at_once_at_the_end_of_the_list(self):
        response = self._add(description="Signed by the Adviser.\nSee https://cit.edu/forms")

        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        self.assertEqual(self._listed_names()[-1], "Adviser's Endorsement")
        slot = UploadSlot.objects.get(pk=response.data["id"])
        self.assertEqual(slot.description, "Signed by the Adviser.\nSee https://cit.edu/forms")
        self.assertFalse(slot.is_required)
        event = self._events(AuditEvent.REQUIREMENT_ADDED).get()
        self.assertEqual(event.user, self.rdco)
        self.assertEqual(event.metadata["name"], "Adviser's Endorsement")
        self.assertEqual(event.metadata["description_characters"], len(slot.description))
        self.assertNotIn("Signed by", str(event.metadata))

    def test_a_requirement_is_never_named_manuscript_or_twice(self):
        for name in ("Manuscript", "  manuscript ", "Release Form", "release form", "", "x" * 201):
            with self.subTest(name=name):
                self.assertEqual(self._add(name=name).status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(self._events(AuditEvent.REQUIREMENT_ADDED).exists())

    def test_the_label_must_be_said(self):
        response = self.client.post(
            f"{BASE}/setup/record-types/{self.thesis.pk}/requirements/", {"name": "Endorsement"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_editing_a_requirement_shows_at_once_and_is_audited(self):
        slot = UploadSlot.objects.get(record_type=self.thesis, name="Ethics Clearance")

        response = self.client.patch(
            f"{BASE}/setup/requirements/{slot.pk}/",
            {"name": "Ethics Clearance Certificate", "is_required": True, "description": "From IERC."},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        listed = self._listed()
        row = next(s for s in listed if s["id"] == slot.pk)
        self.assertEqual((row["name"], row["is_required"], row["description"]),
                         ("Ethics Clearance Certificate", True, "From IERC."))
        changes = self._events(AuditEvent.REQUIREMENT_CHANGED).get().metadata["changes"]
        self.assertEqual(changes["name"], ["Ethics Clearance", "Ethics Clearance Certificate"])
        self.assertEqual(changes["is_required"], [False, True])
        self.assertEqual(changes["description_characters"], [0, len("From IERC.")])

    def test_an_edit_that_changes_nothing_writes_no_event(self):
        slot = UploadSlot.objects.get(record_type=self.thesis, name="Ethics Clearance")
        self.client.patch(f"{BASE}/setup/requirements/{slot.pk}/", {"is_required": False}, format="json")
        self.assertFalse(self._events(AuditEvent.REQUIREMENT_CHANGED).exists())

    def test_only_a_requirements_own_fields_can_be_edited(self):
        slot = UploadSlot.objects.get(record_type=self.thesis, name="Ethics Clearance")
        proposal = RecordType.objects.get(name=RecordTypeName.PROPOSAL)
        response = self.client.patch(
            f"{BASE}/setup/requirements/{slot.pk}/", {"record_type": proposal.pk}, format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        slot.refresh_from_db()
        self.assertEqual(slot.record_type, self.thesis)

    def test_reordering_changes_the_list_everywhere(self):
        ids = list(UploadSlot.objects.filter(record_type=self.thesis, record__isnull=True)
                   .order_by("position").values_list("pk", flat=True))
        reversed_ids = ids[::-1]

        response = self.client.put(
            f"{BASE}/setup/record-types/{self.thesis.pk}/requirements/order/",
            {"order": reversed_ids}, format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        listed = self._listed()
        self.assertEqual([s["id"] for s in listed], reversed_ids)
        self.assertEqual(self._events(AuditEvent.REQUIREMENTS_REORDERED).get().metadata["order"],
                         reversed_ids)

    def test_an_order_must_name_every_requirement_once(self):
        ids = list(UploadSlot.objects.filter(record_type=self.thesis, record__isnull=True)
                   .values_list("pk", flat=True))
        other = UploadSlot.objects.filter(record_type__name=RecordTypeName.PROPOSAL).first().pk
        for order in (ids[:-1], ids + ids[:1], ids[:-1] + [other], "not a list"):
            with self.subTest(order=order):
                response = self.client.put(
                    f"{BASE}/setup/record-types/{self.thesis.pk}/requirements/order/",
                    {"order": order}, format="json",
                )
                self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_an_unused_requirement_is_deleted(self):
        slot = UploadSlot.objects.get(pk=self._add().data["id"])

        response = self.client.delete(f"{BASE}/setup/requirements/{slot.pk}/")

        self.assertEqual(response.data, {"outcome": "deleted"})
        self.assertFalse(UploadSlot.objects.filter(pk=slot.pk).exists())
        self.assertEqual(self._events(AuditEvent.REQUIREMENT_REMOVED).get().metadata["outcome"], "deleted")

    def test_a_used_requirement_is_hidden_and_its_files_stay_on_their_paper(self):
        slot = UploadSlot.objects.get(record_type=self.thesis, name="Release Form")
        record = self._paper()
        kept = RecordUpload.objects.create(record=record, slot=slot, file=upload("release.pdf"),
                                           uploaded_by=self.student)
        setup_row = next(r for r in self._setup()["Thesis / Research"]["requirements"] if r["id"] == slot.pk)
        self.assertTrue(setup_row["in_use"])

        response = self.client.delete(f"{BASE}/setup/requirements/{slot.pk}/")

        self.assertEqual(response.data, {"outcome": "hidden"})
        self.assertTrue(RecordUpload.objects.filter(pk=kept.pk).exists())
        # Gone from Setup and every list ...
        self.assertNotIn("Release Form", self._listed_names())
        self.assertNotIn(slot.pk, [r["id"] for r in self._setup()["Thesis / Research"]["requirements"]])
        self.assertEqual(self.client.patch(f"{BASE}/setup/requirements/{slot.pk}/", {"is_required": True},
                                           format="json").status_code, status.HTTP_404_NOT_FOUND)
        # ... but still on the paper that used it, under its name.
        self.client.force_authenticate(self.student)
        on_paper = self.client.get(f"{BASE}/records/{record.pk}/slots/").data
        row = next(s for s in on_paper if s["id"] == slot.pk)
        self.assertTrue(row["hidden"])
        self.assertEqual([u["id"] for u in row["uploads"]], [kept.pk])
        # A paper that never used it doesn't show it.
        other_paper = self._paper()
        self.assertNotIn(slot.pk, [s["id"] for s in
                                   self.client.get(f"{BASE}/records/{other_paper.pk}/slots/").data])

    def test_a_hidden_requirement_takes_no_new_file(self):
        slot = UploadSlot.objects.get(record_type=self.thesis, name="Release Form")
        record = self._paper()
        RecordUpload.objects.create(record=record, slot=slot, file=upload("release.pdf"),
                                    uploaded_by=self.student)
        self.client.delete(f"{BASE}/setup/requirements/{slot.pk}/")

        self.client.force_authenticate(self.student)
        response = self.client.post(
            f"{BASE}/uploads/create/", {"record": record.pk, "slot": slot.pk, "file": upload("again.pdf")},
            format="multipart",
        )
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(RecordUpload.objects.filter(slot=slot).count(), 1)

    def test_an_ad_hoc_slot_is_not_setups(self):
        record = self._paper()
        adhoc = UploadSlot.objects.create(name="Signed letter", record_type=self.thesis, record=record,
                                          is_required=False)
        response = self.client.patch(f"{BASE}/setup/requirements/{adhoc.pk}/", {"is_required": True},
                                     format="json")
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)


class RecordTypeTextTests(SetupBase):
    def test_rdco_describes_a_record_type_and_its_manuscript(self):
        response = self.client.patch(
            f"{BASE}/setup/record-types/{self.thesis.pk}/",
            {"description": "A Thesis / Research needs a Proposal first.",
             "manuscript_description": "Use the CIT-U format."},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.thesis.refresh_from_db()
        self.assertEqual(self.thesis.description, "A Thesis / Research needs a Proposal first.")
        self.assertEqual(self._setup()["Thesis / Research"]["manuscript"]["description"],
                         "Use the CIT-U format.")
        changes = self._events(AuditEvent.RECORD_TYPE_DESCRIBED).get().metadata["changes"]
        self.assertEqual(set(changes), {"description_characters", "manuscript_description_characters"})

    def test_the_manuscript_cant_be_removed_or_made_optional(self):
        """It is not a slot, and Setup has no field or route that would."""
        response = self.client.patch(
            f"{BASE}/setup/record-types/{self.thesis.pk}/", {"manuscript_required": False}, format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(UploadSlot.objects.filter(name__iexact="manuscript", record__isnull=True,
                                                   record_type=self.thesis).exists())

    def test_a_long_description_is_refused(self):
        response = self.client.patch(
            f"{BASE}/setup/record-types/{self.thesis.pk}/", {"description": "x" * 2001}, format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


class TemplateTests(SetupBase):
    def _put(self, file, slot=None):
        slot = slot or UploadSlot.objects.get(record_type=self.thesis, name="Release Form")
        return self.client.put(f"{BASE}/setup/requirements/{slot.pk}/template/", {"file": file},
                               format="multipart")

    def test_each_accepted_type_is_accepted(self):
        cases = {
            "form.pdf": PDF, "form.docx": DOCX, "form.odt": DOCX, "sheet.xlsx": DOCX, "sheet.ods": DOCX,
            "form.doc": b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"\x00" * 8,
            "sheet.xls": b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"\x00" * 8,
            "sample.png": b"\x89PNG\r\n\x1a\n" + b"\x00" * 8,
            "sample.jpg": b"\xff\xd8\xff\xe0" + b"\x00" * 8, "sample.jpeg": b"\xff\xd8\xff\xe0" + b"\x00" * 8,
        }
        for name, content in cases.items():
            with self.subTest(name=name):
                response = self._put(upload(name, content, "application/octet-stream"))
                self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
                self.assertEqual(response.data["template_name"], name)

    def test_everything_else_is_refused(self):
        cases = {
            "slides.pptx": DOCX, "notes.txt": b"plain", "list.csv": b"a,b", "bundle.zip": DOCX,
            "clip.mp4": b"\x00\x00\x00\x18ftyp", "setup.exe": b"MZ\x90\x00", "run.sh": b"#!/bin/sh",
            "page.html": b"<html>", "noextension": PDF,
            # The right name with the wrong bytes: a program renamed as a form.
            "form.pdf": b"MZ\x90\x00 not a pdf", "form.docx": PDF, "sample.png": PDF,
        }
        for name, content in cases.items():
            with self.subTest(name=name):
                self.assertEqual(self._put(upload(name, content)).status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(self._events(AuditEvent.TEMPLATE_REPLACED).exists())

    def test_an_empty_file_or_none_is_refused(self):
        self.assertEqual(self._put(upload("form.pdf", b"")).status_code, status.HTTP_400_BAD_REQUEST)
        slot = UploadSlot.objects.get(record_type=self.thesis, name="Release Form")
        response = self.client.put(f"{BASE}/setup/requirements/{slot.pk}/template/", {}, format="multipart")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_a_file_over_50_mb_is_refused(self):
        big = upload("form.pdf")
        big.size = MAX_TEMPLATE_BYTES + 1
        self.assertIn("50 MB", template_problem(big))
        exact = upload("form.pdf")
        exact.size = MAX_TEMPLATE_BYTES
        self.assertIsNone(template_problem(exact))

    def test_a_template_always_downloads_for_anyone_signed_in(self):
        slot = UploadSlot.objects.get(record_type=self.thesis, name="Release Form")
        self._put(upload("Release Form v2.pdf"), slot)

        self.client.force_authenticate(self.student)
        response = self.client.get(f"{BASE}/slots/{slot.pk}/template/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response["Content-Disposition"].startswith("attachment"))
        self.assertIn("Release Form v2.pdf", response["Content-Disposition"])
        self.assertEqual(response["X-Content-Type-Options"], "nosniff")
        self.assertEqual(b"".join(response.streaming_content), PDF)
        self.assertFalse(self._events(AuditEvent.DOWNLOAD).exists())

    def test_only_the_newest_template_is_offered_and_the_old_file_goes(self):
        slot = UploadSlot.objects.get(record_type=self.thesis, name="Release Form")
        with self.captureOnCommitCallbacks(execute=True):
            self._put(upload("old.pdf", PDF + b"old"), slot)
        slot.refresh_from_db()
        old_name, storage = slot.template.name, slot.template.storage

        with self.captureOnCommitCallbacks(execute=True):
            self._put(upload("new.pdf", PDF + b"new"), slot)

        self.assertFalse(storage.exists(old_name))
        response = self.client.get(f"{BASE}/slots/{slot.pk}/template/")
        self.assertEqual(b"".join(response.streaming_content), PDF + b"new")
        events = self._events(AuditEvent.TEMPLATE_REPLACED)
        self.assertEqual([e.metadata["replaced"] for e in events], [False, True])
        self.assertEqual(events.last().metadata["filename"], "new.pdf")

    def test_removing_a_template_stops_offering_it(self):
        slot = UploadSlot.objects.get(record_type=self.thesis, name="Release Form")
        self._put(upload(), slot)

        response = self.client.delete(f"{BASE}/setup/requirements/{slot.pk}/template/")

        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertEqual(self.client.get(f"{BASE}/slots/{slot.pk}/template/").status_code,
                         status.HTTP_404_NOT_FOUND)
        self.assertEqual(self._events(AuditEvent.TEMPLATE_REMOVED).get().metadata["target"], "requirement")

    def test_a_hidden_requirements_template_is_not_offered(self):
        slot = UploadSlot.objects.get(record_type=self.thesis, name="Release Form")
        self._put(upload(), slot)
        RecordUpload.objects.create(record=self._paper(), slot=slot, file=upload("r.pdf"),
                                    uploaded_by=self.student)
        self.client.delete(f"{BASE}/setup/requirements/{slot.pk}/")

        self.assertEqual(self.client.get(f"{BASE}/slots/{slot.pk}/template/").status_code,
                         status.HTTP_404_NOT_FOUND)

    def test_the_manuscript_has_a_template_too(self):
        url = f"{BASE}/setup/record-types/{self.thesis.pk}/manuscript-template/"
        response = self.client.put(url, {"file": upload("Thesis format.docx", DOCX)}, format="multipart")

        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual(response.data["manuscript"]["template_name"], "Thesis format.docx")
        self.client.force_authenticate(self.student)
        download = self.client.get(f"{BASE}/record-types/{self.thesis.pk}/manuscript-template/")
        self.assertTrue(download["Content-Disposition"].startswith("attachment"))
        self.assertEqual(
            download["Content-Type"],
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )
        event = self._events(AuditEvent.TEMPLATE_REPLACED).get()
        self.assertEqual((event.metadata["target"], event.metadata["record_type"]), ("manuscript", self.thesis.pk))

        self.client.force_authenticate(self.rdco)
        self.assertEqual(self.client.delete(url).status_code, status.HTTP_204_NO_CONTENT)
        self.assertEqual(self._setup()["Thesis / Research"]["manuscript"]["template_name"], "")
