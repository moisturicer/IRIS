"""
Malware scanning of every upload, before it is stored (IR-666, ADR-072).

Every path that stores bytes a person sent asks `scan_problem(file)` beside
the PDF checks (`validators.pdf_upload_problem`): `None` means it may be
stored; a sentence means it is refused with that sentence, and nothing is
written. A file flagged unsafe is never stored, so it can never be downloaded,
previewed or extracted: refusal is the quarantine (ADR-072 decision 2).

**Fail closed.** A scanner that doesn't answer, or answers an error, refuses
the upload (decision 3). With `DEBUG` off there is no way to turn scanning
off: `configured_scanner` refuses to run without `MALWARE_SCAN=clamd` and a
host. With `DEBUG` on, `MALWARE_SCAN=off` lets a teammate develop without the
1.5 GB container; each upload it lets through is logged as unscanned.

The scanner is ClamAV's `clamd`, reached over TCP with `INSTREAM`
(`ClamdScanner`), in its own container (`clamav` in Compose). Tests install
`FakeScanner`, which flags the real EICAR test string.
"""
from __future__ import annotations

import hashlib
import logging
import socket
import struct
from contextlib import contextmanager
from io import BytesIO
from dataclasses import dataclass
from typing import BinaryIO, Callable, Optional, Protocol

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured

logger = logging.getLogger(__name__)

UNSAFE = "This file was flagged as unsafe and was not uploaded."
UNAVAILABLE = "File checking is temporarily unavailable. Please try again shortly."
#: A stored file the one-time scan took out of use (decision 4): its row stays, without the file.
FILE_GONE = "This file is no longer available."

#: The EICAR test file (eicar.org): harmless, and flagged by every scanner.
#: Built from parts so this source file isn't itself flagged.
EICAR = (
    b"X5O!P%@AP[4\\PZX54(P^)7CC)7}$"
    + b"EICAR-STANDARD-ANTIVIRUS-TEST-FILE!$H+H*"
)

_CHUNK = 64 * 1024


class ScanUnavailable(Exception):
    """The scanner didn't answer, or answered an error: never a clean verdict."""


@dataclass(frozen=True)
class Verdict:
    clean: bool
    #: The signature found; empty when clean.
    signature: str = ""
    #: Filled in by `scan_problem`, for the audit.
    sha256: str = ""
    size: int = 0


class Scanner(Protocol):
    def scan(self, stream: BinaryIO) -> Verdict: ...


class ClamdScanner:
    """clamd over TCP, `zINSTREAM`: the bytes in chunks, then a zero length."""

    def __init__(self, host: str, port: int, *, timeout: float, chunk: int = _CHUNK):
        self.host, self.port, self.timeout, self.chunk = host, port, timeout, chunk

    def scan(self, stream: BinaryIO) -> Verdict:
        try:
            with socket.create_connection((self.host, self.port), timeout=self.timeout) as conn:
                conn.sendall(b"zINSTREAM\0")
                while True:
                    data = stream.read(self.chunk)
                    if not data:
                        break
                    conn.sendall(struct.pack("!L", len(data)) + data)
                conn.sendall(struct.pack("!L", 0))
                answer = b""
                while not answer.endswith(b"\0"):
                    part = conn.recv(4096)
                    if not part:
                        break
                    answer += part
        except OSError as exc:
            raise ScanUnavailable(f"clamd did not answer: {exc}") from exc
        return _read_answer(answer.rstrip(b"\0").decode("utf-8", "replace").strip())


def _read_answer(text: str) -> Verdict:
    # "stream: OK" | "stream: <signature> FOUND" | "<reason> ERROR"
    body = text.split(":", 1)[1].strip() if ":" in text else text
    if body == "OK":
        return Verdict(clean=True)
    if body.endswith(" FOUND"):
        return Verdict(clean=False, signature=body[: -len(" FOUND")].strip())
    raise ScanUnavailable(f"clamd answered {text!r}")


class FakeScanner:
    """
    For tests. Flags a file that starts with the EICAR string, as ClamAV does
    (a PDF carrying it in a comment passes real ClamAV, checked 2026-11-16),
    or, given a `marker`, any file containing it, so a test can send a valid
    PDF or image that the scan refuses. `down` answers nothing.
    """

    def __init__(self, *, down: bool = False, marker: Optional[bytes] = None):
        self.down, self.marker = down, marker

    def scan(self, stream: BinaryIO) -> Verdict:
        if self.down:
            raise ScanUnavailable("the test scanner is down")
        data = stream.read()
        if data.startswith(EICAR):
            return Verdict(clean=False, signature="Eicar-Test-Signature")
        if self.marker is not None and self.marker in data:
            return Verdict(clean=False, signature="Iris-Test-Marker")
        return Verdict(clean=True)


def configured_scanner() -> Optional[Scanner]:
    """The scanner settings name, or None when development switched it off."""
    mode = str(getattr(settings, "MALWARE_SCAN", "clamd") or "").strip().lower()
    if mode == "off":
        if not settings.DEBUG:
            raise ImproperlyConfigured("MALWARE_SCAN=off is allowed only with DEBUG on (ADR-072).")
        return None
    if mode != "clamd":
        raise ImproperlyConfigured(f"MALWARE_SCAN must be clamd or off, not {mode!r} (ADR-072).")
    host = str(getattr(settings, "MALWARE_SCAN_HOST", "") or "").strip()
    if not host:
        raise ImproperlyConfigured("MALWARE_SCAN_HOST is required to scan uploads (ADR-072).")
    return ClamdScanner(
        host, int(getattr(settings, "MALWARE_SCAN_PORT", 3310)),
        timeout=float(getattr(settings, "MALWARE_SCAN_TIMEOUT_SECONDS", 60)),
    )


_installed: Optional[Scanner] = None


@contextmanager
def use_scanner(scanner: Scanner):
    """Install `scanner` for the duration of the block (tests)."""
    global _installed
    previous = _installed
    _installed = scanner
    try:
        yield scanner
    finally:
        _installed = previous


def current_scanner() -> Optional[Scanner]:
    return _installed if _installed is not None else configured_scanner()


def scan_verdict(file) -> Optional[Verdict]:
    """
    The verdict on `file`, read from its start and left there, with its
    digest and size; None when development switched scanning off. Raises
    `ScanUnavailable` when the scanner can't give one.
    """
    scanner = current_scanner()
    data = _read_all(file)
    if scanner is None:
        logger.warning("Upload stored unscanned: MALWARE_SCAN=off (development only, ADR-072).")
        return None
    verdict = scanner.scan(BytesIO(data))
    return Verdict(verdict.clean, verdict.signature, hashlib.sha256(data).hexdigest(), len(data))


def scan_problem(file, *, on_unsafe: Optional[Callable[[Verdict], None]] = None) -> Optional[str]:
    """
    Why `file` may not be stored, or None. `on_unsafe` receives the verdict
    of a flagged file, so the caller can audit it with who sent it and where.
    """
    try:
        verdict = scan_verdict(file)
    except ScanUnavailable:
        logger.exception("Upload refused: the malware scanner is unavailable (ADR-072).")
        return UNAVAILABLE
    if verdict is None or verdict.clean:
        return None
    if on_unsafe is not None:
        on_unsafe(verdict)
    return UNSAFE


def _read_all(file) -> bytes:
    """Every byte of an upload or stream, leaving it at its start for whoever stores it."""
    if hasattr(file, "seek"):
        file.seek(0)
    if hasattr(file, "chunks"):
        data = b"".join(file.chunks())
    else:
        data = file.read()
    if hasattr(file, "seek"):
        file.seek(0)
    return data


def upload_problem(file, *, user, where: str, record=None) -> Optional[str]:
    """
    `scan_problem` for a person's upload: a flagged file is refused and the
    refusal audited (`UPLOAD_REFUSED_UNSAFE`) with who sent it, where, and the
    file's digest, size and name, never its bytes. Every intake path calls this.
    """
    def audit(verdict: Verdict) -> None:
        from apps.audit.models import AuditEvent
        from apps.audit.services import create_audit_event

        create_audit_event(AuditEvent.UPLOAD_REFUSED_UNSAFE, user, record=record, metadata={
            "where": where, "filename": str(getattr(file, "name", "") or "")[:255],
            "sha256": verdict.sha256, "size": verdict.size, "signature": verdict.signature,
        })

    return scan_problem(file, on_unsafe=audit)
