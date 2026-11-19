"""
The real ClamAV refuses the EICAR test file and passes a clean PDF (IR-666, ADR-074).

Runs only where a clamd is named in `MALWARE_SCAN_TEST_HOST` (and optionally
`MALWARE_SCAN_TEST_PORT`): CI's `malware-scan` job starts the
`clamav/clamav` image for it. Everywhere else it is skipped, and the test
scanner (conftest.py) stands in.
"""
import os
from io import BytesIO

import pytest

from apps.documents.scanning import EICAR, ClamdScanner, UNSAFE, scan_problem, use_scanner
from apps.documents.testing import real_pdf_bytes

HOST = os.environ.get("MALWARE_SCAN_TEST_HOST", "")
pytestmark = pytest.mark.skipif(not HOST, reason="no clamd named in MALWARE_SCAN_TEST_HOST")


@pytest.fixture
def clamav():
    scanner = ClamdScanner(HOST, int(os.environ.get("MALWARE_SCAN_TEST_PORT", "3310")), timeout=60)
    with use_scanner(scanner):
        yield scanner


def test_clamav_flags_the_eicar_file(clamav):
    verdict = clamav.scan(BytesIO(EICAR))
    assert not verdict.clean
    assert "Eicar" in verdict.signature
    assert scan_problem(BytesIO(EICAR)) == UNSAFE


def test_clamav_passes_a_clean_pdf(clamav):
    assert clamav.scan(BytesIO(real_pdf_bytes(b"a clean paper"))).clean
    assert scan_problem(BytesIO(real_pdf_bytes(b"a clean paper"))) is None


def test_clamav_takes_a_file_near_the_upload_cap(clamav):
    # The 50 MB cap (validators.MAX_PDF_SIZE_BYTES) must fit clamd's stream limit.
    assert clamav.scan(BytesIO(b"\0" * (49 * 1024 * 1024))).clean
