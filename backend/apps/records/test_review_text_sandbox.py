"""The review text reader runs in the IR-830 sandbox, never in this process (IR-871).

The real subprocess needs Linux (RLIMIT_AS), so those tests skip elsewhere and
run in CI; the refusals that come before the subprocess run everywhere.
"""
import sys
from io import BytesIO

import pytest
from django.test import override_settings

from apps.records.review_text import sandbox
from apps.records.review_text.testing import THESIS, blank, pdf

linux = pytest.mark.skipif(sys.platform != "linux", reason="the sandbox needs Linux RLIMIT_AS")


@linux
def test_a_thesis_is_read_in_the_sandbox():
    outcome = sandbox.read_in_sandbox(BytesIO(pdf(THESIS)))
    assert outcome.state == sandbox.READ, outcome
    keys = [s["key"] for s in outcome.reading["sections"]]
    assert "statement of the problem" in keys


@linux
def test_a_pdf_in_an_embedded_font_is_read_in_the_sandbox():
    """A word processor's PDF maps its font to Unicode through a ToUnicode CMap,
    which pdfminer decodes as UTF-16BE once the sandbox is closed (IR-1005)."""
    outcome = sandbox.read_in_sandbox(BytesIO(pdf(THESIS, embedded=True)))
    assert outcome.state == sandbox.READ, outcome
    keys = [s["key"] for s in outcome.reading["sections"]]
    assert "statement of the problem" in keys


@linux
def test_once_confined_the_child_can_still_decode_every_encoding_a_read_uses():
    """Every codec is loaded before `confine()`, when its module can still be
    opened: decoding empty bytes takes CPython's fast path and loads nothing
    (IR-1005). Run as the sandbox runs the reader, isolated."""
    import subprocess
    from pathlib import Path

    reader_path = Path(sandbox.__file__).with_name("reader.py")
    probe = (
        "import importlib.util\n"
        f"spec = importlib.util.spec_from_file_location('reader', {str(reader_path)!r})\n"
        "reader = importlib.util.module_from_spec(spec); spec.loader.exec_module(reader)\n"
        "reader._preload()\n"
        "reader.confine()\n"
        "for codec in ('UTF-16BE', 'utf-16be', 'utf-16le', 'utf-16', 'latin-1', 'ascii', 'cp1252', 'utf-8'):\n"
        "    try:\n"
        "        'Recharge'.encode(codec).decode(codec)\n"
        "    except Exception as exc:\n"
        "        print('FAILED', codec, type(exc).__name__)\n"
        "print('done')\n"
    )
    result = subprocess.run([sys.executable, "-I", "-c", probe], capture_output=True, text=True, timeout=30)
    assert result.stdout.strip() == "done", result.stdout + result.stderr


@linux
def test_a_scan_reads_as_no_text():
    outcome = sandbox.read_in_sandbox(BytesIO(blank()))
    assert (outcome.state, outcome.reason) == (sandbox.NO_TEXT, "no_text_layer")


@linux
def test_a_broken_file_is_unreadable():
    outcome = sandbox.read_in_sandbox(BytesIO(b"%PDF-1.7 not a real document"))
    assert (outcome.state, outcome.reason) == (sandbox.NO_TEXT, "unreadable")


@linux
@pytest.mark.parametrize("limit", [
    {"REVIEW_TEXT_WALL_SECONDS": 0.001},
    {"REVIEW_TEXT_MEMORY_MIB": 1},
    {"REVIEW_TEXT_MAX_PAGES": 2},
])
def test_each_limit_stops_the_read(limit):
    with override_settings(**limit):
        outcome = sandbox.read_in_sandbox(BytesIO(pdf(THESIS)))
    assert (outcome.state, outcome.reason) == (sandbox.NO_TEXT, "over_limits")


@pytest.mark.parametrize("unset", sandbox.LIMIT_NAMES)
def test_an_unset_limit_reads_nothing(unset):
    with override_settings(**{unset: None}):
        outcome = sandbox.read_in_sandbox(BytesIO(pdf(THESIS)))
    assert (outcome.state, outcome.reason) == (sandbox.UNAVAILABLE, "limits_unset")


@pytest.mark.parametrize("value", [0, -1, float("inf"), True, 1.5])
def test_a_limit_must_be_finite_positive_and_whole_where_it_counts(value):
    with override_settings(REVIEW_TEXT_MEMORY_MIB=value), pytest.raises(ValueError):
        sandbox.limits()


def test_off_linux_nothing_is_read_in_process(monkeypatch):
    monkeypatch.setattr(sys, "platform", "win32")
    outcome = sandbox.read_in_sandbox(BytesIO(pdf(THESIS)))
    assert (outcome.state, outcome.reason) == (sandbox.UNAVAILABLE, "sandbox_unsupported")


@pytest.mark.parametrize("reading", [
    None,
    {"reader": "r", "page_count": 1, "warnings": [], "sections": "no"},
    {"reader": "r", "page_count": 1, "warnings": [], "sections": [
        {"key": "a", "heading": "", "page": 1, "text_hash": "h",
         "passages": [{"text": "x", "page": 1, "paragraph": 1, "kind": "sentence",
                       "regions": [{"page": 1, "left": 0, "top": 0, "right": 2, "bottom": 1}]}]},
    ]},
    {"reader": "r", "page_count": 1, "warnings": [], "sections": [
        # Two sections with one key: everything else is valid.
        {"key": "a", "heading": "", "page": 1, "text_hash": "0" * 64, "passages": []},
        {"key": "a", "heading": "", "page": 1, "text_hash": "0" * 64, "passages": []},
    ]},
])
def test_output_of_the_wrong_shape_is_never_stored(reading):
    # No text, not "unavailable": the same file gives the same output, so a retry can't help.
    outcome = sandbox.outcome_of(reading)
    assert (outcome.state, outcome.reason, outcome.reading) == (sandbox.NO_TEXT, "invalid_output", {})


@linux
def test_once_confined_the_child_can_open_nothing_else():
    """A taken-over parser has nothing to read: not the worker's environment, not
    another file (IR-871 review). Run as the sandbox runs the reader, isolated."""
    import subprocess
    from pathlib import Path

    reader_path = Path(sandbox.__file__).with_name("reader.py")
    probe = (
        "import importlib.util, os, sys\n"
        f"spec = importlib.util.spec_from_file_location('reader', {str(reader_path)!r})\n"
        "reader = importlib.util.module_from_spec(spec); spec.loader.exec_module(reader)\n"
        "reader.confine()\n"
        f"for target in (f'/proc/{{os.getppid()}}/environ', '/etc/hostname', {str(reader_path)!r}):\n"
        "    try:\n"
        "        open(target, 'rb')\n"
        "    except OSError as exc:\n"
        "        print('refused', exc.errno)\n"
        "    else:\n"
        "        print('OPENED', target)\n"
    )
    result = subprocess.run([sys.executable, "-I", "-c", probe], capture_output=True, text=True, timeout=30)
    import errno
    assert result.stdout.split("\n")[:3] == [f"refused {errno.EMFILE}"] * 3, result.stdout + result.stderr
