"""
Tests for document access control (IR-152 / S-01).

Two groups, and they are different kinds of test:

`PublicMediaRouteRemovedTests` is a *regression guard on configuration*. It reads
`frontend/nginx.conf` and `backend/config/urls.py` as text. That is unusual, and
it is deliberate: the vulnerability this ticket closes did not live in Python at
all -- nginx served the media volume directly, bypassing every permission check
in `documents/views.py`. A Django test client cannot reach nginx, and there is no
CI or infrastructure test suite to catch a reinstated location block (IR-82,
IR-163). Asserting on the config text is the only automated guard available, so
it is better than the alternative, which is no guard.

`DocumentDownloadPermissionTests` covers the other half of the ticket: that
removing the public route does not remove legitimate access, and that the
authenticated path really does discriminate between an owner and a stranger.
These are characterisation tests -- the permission checks already existed and
already passed. They are here so that the guarantee the deletion relies on is
pinned down rather than assumed.
"""

import shutil
import tempfile

from django.conf import settings
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase, override_settings
from unittest import skipUnless
from rest_framework import status
from rest_framework.test import APITestCase

from apps.accounts.models import User
from apps.documents.models import RecordUpload, UploadSlot
from apps.records.models import Record, RecordOwner, RecordType

def _repo_root():
    """
    The checkout root, or None when it is not reachable.

    The backend container mounts only `backend/` at `/app`, so `nginx.conf` and
    `docker-compose.prod.yml` are outside the filesystem the test process can see.
    Rather than pass vacuously in that environment, the two tests that need them
    skip with a stated reason -- and run for real on a full checkout, which is
    where CI will execute them (IR-163).
    """
    for candidate in (settings.BASE_DIR, *settings.BASE_DIR.parents):
        if (candidate / "frontend").is_dir() and (candidate / "backend").is_dir():
            return candidate
    return None


REPO_ROOT = _repo_root()

NEEDS_CHECKOUT = "requires the repo root; the backend container mounts only backend/"


class PublicMediaRouteRemovedTests(SimpleTestCase):
    """
    Uploaded files must not be reachable at a guessable static path.

    `RecordUpload.file` uses `upload_to="documents/"`, so the stored name derives
    from the uploaded filename. Any public `/media/` route therefore exposes every
    uploaded thesis at `https://<host>/media/documents/<filename>` to anyone who
    can guess a title.
    """

    @skipUnless(REPO_ROOT, NEEDS_CHECKOUT)
    def test_nginx_does_not_serve_media(self):
        """
        The nginx `location /media/` block must not come back.

        This is the actual defect: `frontend/nginx.conf` aliased the media volume
        with a 30-day cache, and `docker-compose.prod.yml` mounted `media_files`
        into the web container read-only to feed it.
        """
        conf = (REPO_ROOT / "frontend" / "nginx.conf").read_text(encoding="utf-8")
        self.assertNotIn(
            "location /media/",
            conf,
            "nginx.conf serves /media/ again -- every uploaded document is public. "
            "Downloads must go through RecordUploadDownloadView / "
            "RecordFileDownloadView, which check ownership.",
        )

    @skipUnless(REPO_ROOT, NEEDS_CHECKOUT)
    def test_prod_compose_does_not_mount_media_into_the_web_container(self):
        """
        The web container has no reason to hold the media volume once nginx stops
        serving it, and mounting it there is what made the leak reachable.
        """
        compose = (REPO_ROOT / "docker-compose.prod.yml").read_text(encoding="utf-8")
        self.assertNotIn(
            "media_files:/usr/share/nginx/html/media",
            compose,
            "the media volume is mounted into the web container again -- nothing "
            "there should be able to read uploaded documents",
        )

    def test_django_does_not_serve_media_in_debug(self):
        """
        `config/urls.py` must not add Django's `static()` media route either.

        Django's test runner forces `DEBUG=False`, so a request-based assertion
        here would pass whether or not the route exists. Reading the URLconf is
        what actually distinguishes the two states. It matters because developers
        run with `DEBUG=True`, and a route that serves every upload unauthenticated
        on a laptop is still a route that serves every upload unauthenticated.
        """
        urlconf = (settings.BASE_DIR / "config" / "urls.py").read_text(encoding="utf-8")
        self.assertNotIn(
            "static(settings.MEDIA_URL",
            urlconf,
            "config/urls.py serves MEDIA_URL under DEBUG -- uploads are "
            "unauthenticated in every developer environment",
        )


@override_settings(MEDIA_ROOT=tempfile.mkdtemp(prefix="iris-test-media-"))
class DocumentDownloadPermissionTests(APITestCase):
    """The authenticated download path must let owners through and turn others away."""

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(settings.MEDIA_ROOT, ignore_errors=True)
        super().tearDownClass()

    @classmethod
    def make_user(cls, email, **extra):
        extra.setdefault("is_verified", True)
        return User.objects.create_user(email=email, password="TestPass123!", **extra)

    def setUp(self):
        self.owner = self.make_user("owner@cit.edu")
        self.stranger = self.make_user("stranger@cit.edu")

        record_type = RecordType.objects.first()
        self.assertIsNotNone(record_type, "no seeded RecordType -- migrations incomplete")

        self.record = Record.objects.create(
            title="Confidential Thesis On Something Valuable",
            record_type=record_type,
            added_by=self.owner,
        )
        RecordOwner.objects.create(record=self.record, user=self.owner, is_primary=True)

        slot = UploadSlot.objects.create(name="Manuscript", record_type=record_type)
        self.upload = RecordUpload.objects.create(
            record=self.record,
            slot=slot,
            file=SimpleUploadedFile("thesis.pdf", b"%PDF-1.4 secret", content_type="application/pdf"),
            uploaded_by=self.owner,
        )
        self.url = f"/api/v1/documents/uploads/{self.upload.pk}/download/"

    def test_owner_can_download(self):
        self.client.force_authenticate(user=self.owner)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_non_owner_is_refused(self):
        """A verified account with no claim on the record is still a stranger to it."""
        self.client.force_authenticate(user=self.stranger)
        response = self.client.get(self.url)
        self.assertEqual(
            response.status_code,
            status.HTTP_403_FORBIDDEN,
            "a non-owner could download another user's upload",
        )

    def test_anonymous_is_refused(self):
        response = self.client.get(self.url)
        self.assertIn(
            response.status_code,
            (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN),
            "the download endpoint answered an unauthenticated caller",
        )
