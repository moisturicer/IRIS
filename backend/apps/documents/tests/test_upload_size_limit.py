"""
nginx must accept the uploads Django accepts (IR-628).

`frontend/nginx.conf` had no `client_max_body_size`, so nginx applied its 1m
default and answered 413 to any thesis PDF before Django saw it, while
`validators.py` allows 50 MiB. Like `PublicMediaRouteRemovedTests`, this reads
the config as text: a Django test client cannot reach nginx, so asserting on the
file is the only automated guard available.
"""

import re
from unittest import skipUnless

from django.test import SimpleTestCase

from apps.documents.tests.test_document_access_control import NEEDS_CHECKOUT, REPO_ROOT
from apps.documents.validators import MAX_PDF_SIZE_BYTES

_UNITS = {"": 1, "k": 1024, "m": 1024 ** 2, "g": 1024 ** 3}


def _body_limits(conf):
    """Every `client_max_body_size` in `conf`, in bytes (0 means unlimited)."""
    return [
        int(number) * _UNITS[unit.lower()]
        for number, unit in re.findall(
            r"^\s*client_max_body_size\s+(\d+)([kKmMgG]?)\s*;", conf, re.MULTILINE
        )
    ]


class NginxBodyLimitTests(SimpleTestCase):
    @skipUnless(REPO_ROOT, NEEDS_CHECKOUT)
    def test_nginx_accepts_a_pdf_at_the_django_limit_and_bounds_the_rest(self):
        conf = (REPO_ROOT / "frontend" / "nginx.conf").read_text(encoding="utf-8")
        limits = _body_limits(conf)

        self.assertEqual(
            len(limits),
            1,
            "nginx.conf should set client_max_body_size exactly once, at server "
            "level -- without it nginx's 1m default rejects every thesis upload",
        )
        (limit,) = limits
        self.assertNotEqual(limit, 0, "an unlimited request body lets anyone fill the disk")
        self.assertGreater(
            limit,
            MAX_PDF_SIZE_BYTES,
            "nginx rejects a PDF that Django's validator would accept; leave room "
            "for multipart framing above MAX_PDF_SIZE_BYTES",
        )
        self.assertLessEqual(
            limit,
            2 * MAX_PDF_SIZE_BYTES,
            "the nginx bound has drifted far above the PDF limit it exists to serve",
        )
