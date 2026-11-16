"""
Every upload is scanned for malware before it is stored (IR-666, ADR-072).

The clamd client is tested against a stand-in server speaking clamd's
INSTREAM protocol on a real socket, so the wire format is pinned without
ClamAV. The real ClamAV is CI's `malware-scan` job, with the EICAR file.
"""
import socket
import struct
import threading
from io import BytesIO

import pytest
from django.core.exceptions import ImproperlyConfigured
from django.test import override_settings

from apps.documents import scanning
from apps.documents.scanning import (
    EICAR, FakeScanner, ClamdScanner, ScanUnavailable, UNAVAILABLE, UNSAFE, scan_problem, use_scanner,
)


class StandInClamd:
    """A one-connection clamd that answers INSTREAM with `answer`, or closes."""

    def __init__(self, answer: bytes | None):
        self.answer = answer
        self.received = b""
        self.server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server.bind(("127.0.0.1", 0))
        self.server.listen(1)
        self.port = self.server.getsockname()[1]
        self.thread = threading.Thread(target=self._serve, daemon=True)
        self.thread.start()

    def _serve(self):
        conn, _ = self.server.accept()
        with conn:
            command = b""
            while not command.endswith(b"\0"):
                command += conn.recv(1)
            assert command == b"zINSTREAM\0"
            while True:
                size = struct.unpack("!L", self._exactly(conn, 4))[0]
                if size == 0:
                    break
                self.received += self._exactly(conn, size)
            if self.answer is not None:
                conn.sendall(self.answer)
        self.server.close()

    @staticmethod
    def _exactly(conn, n):
        data = b""
        while len(data) < n:
            chunk = conn.recv(n - len(data))
            if not chunk:
                raise ConnectionError("closed")
            data += chunk
        return data


def test_clamd_streams_the_bytes_and_reads_a_clean_answer():
    clamd = StandInClamd(b"stream: OK\0")
    verdict = ClamdScanner("127.0.0.1", clamd.port, timeout=5, chunk=7).scan(BytesIO(b"%PDF-1.7 a clean paper"))
    clamd.thread.join(5)
    assert verdict.clean and verdict.signature == ""
    assert clamd.received == b"%PDF-1.7 a clean paper"


def test_clamd_names_the_signature_it_found():
    clamd = StandInClamd(b"stream: Win.Test.EICAR_HDB-1 FOUND\0")
    verdict = ClamdScanner("127.0.0.1", clamd.port, timeout=5).scan(BytesIO(EICAR))
    assert not verdict.clean and verdict.signature == "Win.Test.EICAR_HDB-1"


@pytest.mark.parametrize("answer", [b"INSTREAM size limit exceeded. ERROR\0", None])
def test_an_error_or_a_closed_connection_is_unavailable_never_clean(answer):
    clamd = StandInClamd(answer)
    with pytest.raises(ScanUnavailable):
        ClamdScanner("127.0.0.1", clamd.port, timeout=5).scan(BytesIO(b"x"))


def test_nothing_listening_is_unavailable():
    with pytest.raises(ScanUnavailable):
        ClamdScanner("127.0.0.1", 1, timeout=1).scan(BytesIO(b"x"))


def test_the_test_scanner_flags_eicar_where_clamav_does_and_passes_anything_else():
    with use_scanner(FakeScanner()):
        assert scan_problem(BytesIO(EICAR)) == UNSAFE
        # Real ClamAV passes EICAR that isn't at the start (a PDF comment), and so does this.
        assert scan_problem(BytesIO(b"%PDF-1.7 " + EICAR)) is None
        assert scan_problem(BytesIO(b"%PDF-1.7 fine")) is None
    with use_scanner(FakeScanner(marker=b"%IRIS-TEST-MALWARE")):
        assert scan_problem(BytesIO(b"%PDF-1.7 %IRIS-TEST-MALWARE")) == UNSAFE


def test_a_scanner_that_is_down_refuses_the_upload():
    with use_scanner(FakeScanner(down=True)):
        assert scan_problem(BytesIO(b"%PDF-1.7 fine")) == UNAVAILABLE


def test_the_file_is_read_from_the_start_and_left_there():
    upload = BytesIO(b"%PDF-1.7 fine")
    upload.seek(5)
    with use_scanner(FakeScanner()):
        assert scan_problem(upload) is None
    assert upload.tell() == 0


def test_a_verdict_is_reported_for_the_audit():
    seen = []
    with use_scanner(FakeScanner()):
        scan_problem(BytesIO(EICAR), on_unsafe=seen.append)
    assert seen[0].signature == "Eicar-Test-Signature" and len(seen[0].sha256) == 64


@override_settings(DEBUG=False, MALWARE_SCAN="off", MALWARE_SCAN_HOST="")
def test_production_refuses_to_run_without_a_scanner():
    with pytest.raises(ImproperlyConfigured):
        scanning.configured_scanner()


@override_settings(DEBUG=False, MALWARE_SCAN="clamd", MALWARE_SCAN_HOST="")
def test_production_refuses_clamd_with_no_host():
    with pytest.raises(ImproperlyConfigured):
        scanning.configured_scanner()


@override_settings(DEBUG=True, MALWARE_SCAN="off", MALWARE_SCAN_HOST="")
def test_development_may_switch_scanning_off():
    assert scanning.configured_scanner() is None


@override_settings(DEBUG=False, MALWARE_SCAN="clamd", MALWARE_SCAN_HOST="clamav", MALWARE_SCAN_PORT=3310)
def test_production_scans_with_clamd():
    scanner = scanning.configured_scanner()
    assert isinstance(scanner, ClamdScanner) and scanner.host == "clamav" and scanner.port == 3310
