"""
My Templates: Advisers share proposal Templates (ADR-063 decision 8, IR-975).

Who may call each route is the access matrix's (`apps/tests/test_access_matrix.py`).
These pin what the routes do: an Adviser keeps their own list, in their own order,
under Setup's file rules and the malware scan; nobody else, RDCO included, can
change or remove one; everyone signed in reads the shown ones, and an Adviser who
is suspended, deleted or no longer an Adviser shows none; every change is audited.
"""

import shutil
import tempfile

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from apps.accounts.models import Role, User
from apps.audit.models import AuditEvent
from apps.documents.models import AdviserTemplate
from apps.documents.scanning import UNSAFE, FakeScanner, use_scanner

MINE = "/api/v1/documents/my-templates"
SHOWN = "/api/v1/documents/adviser-templates"
PDF = b"%PDF-1.4\n% a proposal format\n"
DOCX = b"PK\x03\x04" + b"\x00" * 26
MARKER = b"%IRIS-TEST-MALWARE"


def upload(name="format.pdf", content=PDF, content_type="application/pdf"):
    return SimpleUploadedFile(name, content, content_type=content_type)


class AdviserTemplateBase(APITestCase):
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
        scanner = use_scanner(FakeScanner(marker=MARKER))
        scanner.__enter__()
        self.addCleanup(scanner.__exit__, None, None, None)
        self.adviser = self._user("templates-adviser@cit.edu", "Adviser", "Ada")
        self.client.force_authenticate(self.adviser)

    def _user(self, email, role, first="Test"):
        return User.objects.create_user(
            email=email, password="TestPass123!", is_verified=True,
            first_name=first, last_name=role.title(),
            role=Role.objects.get_or_create(name=role)[0],
        )

    def _add(self, title="Proposal format", description="", file=None):
        return self.client.post(
            f"{MINE}/", {"title": title, "description": description, "file": file or upload()},
            format="multipart",
        )

    def _mine(self):
        response = self.client.get(f"{MINE}/")
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        return response.data

    def _events(self, event_type):
        return AuditEvent.objects.filter(event_type=event_type)


class AnAdviserAddsTemplatesTests(AdviserTemplateBase):
    def test_an_added_template_is_listed_with_its_title_description_and_file_name(self):
        response = self._add("Chapter 1 format", "Use this for Chapter 1.\nSee https://cit.edu/forms.",
                             upload("Chapter 1 format.docx", DOCX))

        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        (template,) = self._mine()
        self.assertEqual(
            (template["title"], template["description"], template["file_name"], template["position"]),
            ("Chapter 1 format", "Use this for Chapter 1.\nSee https://cit.edu/forms.", "Chapter 1 format.docx", 1),
        )

    def test_templates_are_listed_in_the_order_they_were_added(self):
        self._add("First")
        self._add("Second")

        self.assertEqual([t["title"] for t in self._mine()], ["First", "Second"])

    def test_a_title_and_a_file_are_required(self):
        no_title = self._add(title="  ")
        no_file = self.client.post(f"{MINE}/", {"title": "No file"}, format="multipart")

        self.assertEqual(no_title.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(no_file.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(AdviserTemplate.objects.exists())

    def test_a_file_setup_would_refuse_is_refused(self):
        """The same file rules as Setup's Templates (ADR-063 decision 8)."""
        for name, content, why in (
            ("notes.txt", b"plain text", "type"),
            ("format.pdf", b"MZ\x90\x00 a program", "contents"),
            ("format.pdf", b"", "empty"),
        ):
            with self.subTest(why):
                response = self._add(file=upload(name, content))
                self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST, response.data)
        self.assertFalse(AdviserTemplate.objects.exists())

    def test_a_file_the_malware_scan_flags_is_refused_stored_nowhere_and_audited(self):
        response = self._add(file=upload(content=PDF + MARKER))

        self.assertEqual((response.status_code, response.data["detail"]), (status.HTTP_400_BAD_REQUEST, UNSAFE))
        self.assertFalse(AdviserTemplate.objects.exists())
        (event,) = self._events(AuditEvent.UPLOAD_REFUSED_UNSAFE)
        self.assertEqual((event.user, event.metadata["where"]), (self.adviser, "my_template"))


class AnAdviserChangesTheirTemplatesTests(AdviserTemplateBase):
    def setUp(self):
        super().setUp()
        self.first = self._add("First", "Short.").data
        self.second = self._add("Second").data

    def test_the_title_and_description_can_be_edited_and_the_change_is_audited_without_its_text(self):
        response = self.client.patch(f"{MINE}/{self.first['id']}/",
                                     {"title": "Renamed", "description": "A longer note."}, format="json")

        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual([(t["title"], t["description"]) for t in self._mine()][0], ("Renamed", "A longer note."))
        event = self._events(AuditEvent.ADVISER_TEMPLATE_CHANGED).get()
        self.assertEqual(event.user, self.adviser)
        self.assertEqual(event.metadata["changes"],
                         {"title": ["First", "Renamed"], "description_characters": [6, 14]})
        self.assertNotIn("A longer note.", str(event.metadata))

    def test_replacing_the_file_offers_only_the_new_one(self):
        response = self.client.patch(f"{MINE}/{self.first['id']}/",
                                     {"file": upload("v2.docx", DOCX)}, format="multipart")

        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        download = self.client.get(f"{SHOWN}/{self.first['id']}/file/")
        self.assertEqual(download.status_code, status.HTTP_200_OK)
        self.assertEqual(b"".join(download.streaming_content), DOCX)
        self.assertIn('filename="v2.docx"', download["Content-Disposition"])
        event = self._events(AuditEvent.ADVISER_TEMPLATE_CHANGED).get()
        self.assertEqual(event.metadata["changes"]["file"], ["format.pdf", "v2.docx"])

    def test_a_replaced_file_leaves_storage_once_the_change_commits(self):
        old = AdviserTemplate.objects.get(pk=self.first["id"]).file
        self.assertTrue(old.storage.exists(old.name))
        with self.captureOnCommitCallbacks(execute=True):
            self.client.patch(f"{MINE}/{self.first['id']}/", {"file": upload("v2.docx", DOCX)}, format="multipart")

        self.assertFalse(old.storage.exists(old.name))
        new = AdviserTemplate.objects.get(pk=self.first["id"]).file
        self.assertTrue(new.storage.exists(new.name))

    def test_the_adviser_downloads_their_own_file_even_while_it_is_not_shown(self):
        """An Adviser not yet verified opens My Templates but shows nothing to others."""
        User.objects.filter(pk=self.adviser.pk).update(is_verified=False)

        own = self.client.get(f"{MINE}/{self.first['id']}/file/")
        self.assertEqual(own.status_code, status.HTTP_200_OK)
        self.assertEqual(b"".join(own.streaming_content), PDF)
        self.assertTrue(own["Content-Disposition"].startswith("attachment"))
        self.assertEqual(self.client.get(f"{SHOWN}/{self.first['id']}/file/").status_code, status.HTTP_404_NOT_FOUND)

    def test_a_template_removed_meanwhile_is_not_found(self):
        """Another tab removed it between the lookup and the change: a 404, never a 500."""
        from apps.documents import adviser_templates

        stale = AdviserTemplate.objects.get(pk=self.first["id"])
        AdviserTemplate.objects.filter(pk=stale.pk).delete()
        for change in (lambda: adviser_templates.edit_template(stale, self.adviser, {"title": "Late"}),
                       lambda: adviser_templates.remove_template(stale, self.adviser)):
            with self.assertRaises(adviser_templates.TemplateGone):
                change()

    def test_a_replacement_the_scan_flags_keeps_the_old_file(self):
        response = self.client.patch(f"{MINE}/{self.first['id']}/",
                                     {"file": upload(content=PDF + MARKER)}, format="multipart")

        self.assertEqual((response.status_code, response.data["detail"]), (status.HTTP_400_BAD_REQUEST, UNSAFE))
        download = self.client.get(f"{SHOWN}/{self.first['id']}/file/")
        self.assertEqual(b"".join(download.streaming_content), PDF)

    def test_templates_can_be_reordered_and_the_order_is_audited(self):
        order = [self.second["id"], self.first["id"]]
        response = self.client.put(f"{MINE}/order/", {"order": order}, format="json")

        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual([t["title"] for t in self._mine()], ["Second", "First"])
        event = self._events(AuditEvent.ADVISER_TEMPLATES_REORDERED).get()
        self.assertEqual(event.metadata["order"], order)

    def test_an_order_that_misses_or_repeats_a_template_is_refused(self):
        both = f"{self.first['id']}{self.second['id']}"
        for order in ([self.first["id"]], [self.first["id"], self.first["id"]], ["x"], both, {"a": 1}):
            with self.subTest(order=order):
                response = self.client.put(f"{MINE}/order/", {"order": order}, format="json")
                self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual([t["title"] for t in self._mine()], ["First", "Second"])

    def test_a_removed_template_is_gone_with_its_file_and_audited(self):
        stored = AdviserTemplate.objects.get(pk=self.first["id"]).file
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.delete(f"{MINE}/{self.first['id']}/")

        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(stored.storage.exists(stored.name))
        self.assertEqual([t["title"] for t in self._mine()], ["Second"])
        self.assertEqual(self.client.get(f"{SHOWN}/{self.first['id']}/file/").status_code,
                         status.HTTP_404_NOT_FOUND)
        event = self._events(AuditEvent.ADVISER_TEMPLATE_REMOVED).get()
        self.assertEqual((event.user, event.metadata["title"]), (self.adviser, "First"))

    def test_adding_is_audited_without_the_description_text(self):
        event = self._events(AuditEvent.ADVISER_TEMPLATE_ADDED).filter(metadata__title="First").get()

        self.assertEqual(event.user, self.adviser)
        self.assertEqual(event.metadata["description_characters"], len("Short."))
        self.assertNotIn("Short.", str(event.metadata))


class NobodyElseChangesAnAdvisersTemplatesTests(AdviserTemplateBase):
    """RDCO cannot remove an Adviser's Template (ADR-063 decision 8), nor can another Adviser."""

    def setUp(self):
        super().setUp()
        self.template = self._add("Ada's format").data

    def test_rdco_and_another_adviser_can_neither_change_nor_remove_it(self):
        # RDCO is refused by the role gate; another Adviser finds nothing of theirs.
        for someone, refused in ((self._user("templates-rdco@cit.edu", "RDCO"), status.HTTP_403_FORBIDDEN),
                                 (self._user("templates-other@cit.edu", "Adviser", "Ben"), status.HTTP_404_NOT_FOUND)):
            with self.subTest(someone.role.name):
                self.client.force_authenticate(someone)
                edit = self.client.patch(f"{MINE}/{self.template['id']}/", {"title": "Mine now"}, format="json")
                remove = self.client.delete(f"{MINE}/{self.template['id']}/")
                own_file = self.client.get(f"{MINE}/{self.template['id']}/file/")
                self.assertEqual((edit.status_code, remove.status_code, own_file.status_code), (refused,) * 3)
        self.assertEqual(AdviserTemplate.objects.get().title, "Ada's format")
        self.assertFalse(self._events(AuditEvent.ADVISER_TEMPLATE_REMOVED).exists())

    def test_another_advisers_list_and_order_never_include_it(self):
        self.client.force_authenticate(self._user("templates-other@cit.edu", "Adviser", "Ben"))

        self.assertEqual(self._mine(), [])
        response = self.client.put(f"{MINE}/order/", {"order": [self.template["id"]]}, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


class WhoseTemplatesShowTests(AdviserTemplateBase):
    """
    Everyone signed in sees an Adviser's Templates, until the Adviser is suspended,
    deleted or no longer an Adviser (ADR-063 decision 8): then they stop showing
    everywhere, the list and the download alike.
    """

    def setUp(self):
        super().setUp()
        self.template = self._add("Ada's format").data
        self.client.force_authenticate(self._user("templates-student@cit.edu", "Student"))

    def _shown_titles(self):
        response = self.client.get(f"{SHOWN}/")
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        return [t["title"] for t in response.data]

    def _downloads(self):
        return self.client.get(f"{SHOWN}/{self.template['id']}/file/").status_code == status.HTTP_200_OK

    def test_anyone_signed_in_sees_and_downloads_an_active_advisers_template(self):
        response = self.client.get(f"{SHOWN}/")

        (shown,) = response.data
        self.assertEqual((shown["title"], shown["shared_by"]["id"]), ("Ada's format", self.adviser.pk))
        download = self.client.get(f"{SHOWN}/{self.template['id']}/file/")
        self.assertEqual(download.status_code, status.HTTP_200_OK)
        self.assertTrue(download["Content-Disposition"].startswith("attachment"))

    def test_an_adviser_who_is_suspended_deleted_or_no_longer_an_adviser_shows_none(self):
        adviser_role = Role.objects.get(name="Adviser")
        student_role = Role.objects.get_or_create(name="Student")[0]
        for why, change in (
            ("suspended", {"is_active": False}),
            ("locked", {"is_locked": True}),
            ("deleted", {"deleted_at": timezone.now()}),
            ("no longer an Adviser", {"role": student_role}),
        ):
            with self.subTest(why):
                User.objects.filter(pk=self.adviser.pk).update(**change)
                self.assertEqual(self._shown_titles(), [])
                self.assertFalse(self._downloads())
                User.objects.filter(pk=self.adviser.pk).update(
                    is_active=True, is_locked=False, deleted_at=None, role=adviser_role,
                )
                self.assertEqual(self._shown_titles(), ["Ada's format"])
                self.assertTrue(self._downloads())

    def test_only_an_adviser_reaches_my_templates(self):
        self.assertEqual(self.client.get(f"{MINE}/").status_code, status.HTTP_403_FORBIDDEN)
