"""Running the evidence reader in its sandbox (IR-1053).

The real child needs Linux (RLIMIT_AS); those tests skip elsewhere.
"""
import sys

import pytest
from django.test import override_settings

from apps.ai.extraction.tests.fixtures import FIXTURES, pdf_bytes
from apps.documents.pdf_evidence import sandbox
from apps.documents.pdf_evidence.tests.thesis import thesis_pdf

pytestmark = pytest.mark.django_required
linux = pytest.mark.skipif(sys.platform != "linux", reason="the sandbox needs Linux RLIMIT_AS")

LIMITS = {"PDF_EVIDENCE_WALL_SECONDS": 60, "PDF_EVIDENCE_MEMORY_MIB": 1024, "PDF_VALIDATION_MAX_PAGES": 1000}


def empty_with(error):
    return {"reader": sandbox.READER, "error": error, "page_count": 0, "pages": [],
            "bookmarks": [], "page_labels": None, "contents": []}


@pytest.mark.parametrize("unset", ["PDF_EVIDENCE_WALL_SECONDS", "PDF_EVIDENCE_MEMORY_MIB",
                                   "PDF_VALIDATION_MAX_PAGES"])
def test_an_unset_limit_reads_nothing(unset):
    with override_settings(**{**LIMITS, unset: None}):
        assert sandbox.read_pdf_evidence(thesis_pdf()) == empty_with("limits_unset")


@override_settings(**LIMITS)
def test_a_file_over_the_upload_size_is_not_read(monkeypatch):
    monkeypatch.setattr(sandbox, "MAX_SOURCE_BYTES", 10)
    assert sandbox.read_pdf_evidence(thesis_pdf()) == empty_with("over_limits")


def test_output_of_the_wrong_shape_is_refused():
    good = {"reader": sandbox.READER, "error": "", "page_count": 1,
            "pages": [{"page": 1, "width": 612.0, "height": 792.0, "has_text_layer": False}],
            "bookmarks": [], "page_labels": None, "contents": []}
    assert sandbox.valid(good)
    assert not sandbox.valid({**good, "pages": [{"page": "1"}]})
    assert not sandbox.valid({**good, "bookmarks": [{"title": 1, "level": 1, "page": 1}]})
    assert not sandbox.valid({**good, "page_labels": "i"})
    assert not sandbox.valid({**good, "page_labels": ["i", "ii"]})
    assert not sandbox.valid({**good, "pages": [{**good["pages"][0], "page": 2}]})
    assert not sandbox.valid({**good, "extra": True})


@linux
@override_settings(**LIMITS)
def test_the_child_reads_a_thesis():
    evidence = sandbox.read_pdf_evidence(thesis_pdf())

    assert evidence["error"] == ""
    assert evidence["page_labels"] == ["i", "ii", "iii", "1", "2"]
    assert [b["title"] for b in evidence["bookmarks"]][:2] == ["Contents", "1 Introduction"]
    assert len(evidence["contents"]) == 4


@linux
@override_settings(**LIMITS)
def test_the_child_reads_every_extraction_fixture():
    for fixture in FIXTURES.values():
        evidence = sandbox.read_pdf_evidence(pdf_bytes(fixture))
        assert evidence["error"] == "" and evidence["pages"][0]["lines"], fixture.name


@linux
@override_settings(**LIMITS)
def test_a_malformed_pdf_records_unreadable():
    assert sandbox.read_pdf_evidence(b"%PDF-1.7 not really a pdf") == empty_with("unreadable")


@linux
@override_settings(**{**LIMITS, "PDF_VALIDATION_MAX_PAGES": 2})
def test_more_pages_than_the_limit_records_over_limits():
    assert sandbox.read_pdf_evidence(thesis_pdf()) == empty_with("over_limits")


@linux
def test_once_confined_the_child_can_open_nothing_else():
    """A taken-over parser has nothing to read: not the worker's environment,
    not another file. Run as the sandbox runs the reader, isolated."""
    import errno
    import subprocess
    from pathlib import Path

    reader_path = Path(sandbox.__file__).with_name("reader.py")
    probe = (
        "import importlib.util, os, sys\n"
        f"spec = importlib.util.spec_from_file_location('reader', {str(reader_path)!r})\n"
        "reader = importlib.util.module_from_spec(spec); spec.loader.exec_module(reader)\n"
        "reader._preload(); reader.confine()\n"
        f"for target in (f'/proc/{{os.getppid()}}/environ', '/etc/hostname', {str(reader_path)!r}):\n"
        "    try:\n"
        "        open(target, 'rb')\n"
        "    except OSError as exc:\n"
        "        print('refused', exc.errno)\n"
        "    else:\n"
        "        print('OPENED', target)\n"
    )
    result = subprocess.run([sys.executable, "-I", "-c", probe], capture_output=True, text=True, timeout=30)
    assert result.stdout.split("\n")[:3] == [f"refused {errno.EMFILE}"] * 3, result.stdout + result.stderr
