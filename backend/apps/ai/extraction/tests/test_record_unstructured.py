"""The Unstructured spike recorder (IR-984).

Driven through ``unstructured_vendor.Vendor``, an ``httpx.MockTransport`` that
plays Transform, so the request is really built and the files really written.
No vendor call.
"""

import copy
import json

import httpx
import pytest

from apps.ai.extraction.tests.fixtures.record_unstructured import (
    RecordingFailed,
    measure,
    reading_order_holds,
    record,
)
from apps.ai.extraction.tests.unstructured_vendor import Vendor

PDF = b"%PDF-1.4 synthetic"


def _element(kind, text, page=1, coordinates="box", html=None):
    box = {
        "points": [[10, 20], [10, 40], [200, 40], [200, 20]],
        "system": "PixelSpace",
        "layout_width": 1700,
        "layout_height": 2200,
    }
    return {
        "element_id": f"e-{text[:8]}",
        "type": kind,
        "text": text,
        "metadata": {
            "page_number": page,
            "coordinates": box if coordinates == "box" else coordinates,
            "text_as_html": html,
        },
    }


def _result(elements, status="completed", warnings=()):
    return {
        "id": "job-1",
        "status": status,
        "profile": "balanced",
        "markdown": None,
        "format_version": "2.0",
        "metadata": {"page_count": 1},
        "extracted_data": [],
        "warnings": list(warnings),
        "elements": copy.deepcopy(elements),
        "source": {
            "file_id": "file-1",
            "filename": "two_columns.pdf",
            "mimetype": "application/pdf",
            "expires_at": "2026-11-14T00:00:00Z",
        },
    }


ELEMENTS = [
    _element("Title", "Two column study"),
    _element("NarrativeText", "Left column one opens."),
    _element("Formula", "E = m c^2", coordinates=None),
]


def _record(vendor, tmp_path, **kwargs):
    with vendor.api() as api:
        return record("two_columns", PDF, tmp_path, api=api, sleep=lambda _: None, **kwargs)


def test_asks_for_elements_with_coordinates_and_table_html(tmp_path):
    vendor = Vendor(result=_result(ELEMENTS))
    _record(vendor, tmp_path)

    parse = vendor.parse_request
    assert parse.url.path == "/api/v2/parse"
    assert parse.url.params.get_list("include") == ["coordinates", "table_html"]
    body = parse.content
    assert b'name="output"\r\n\r\nelements' in body
    assert b'name="profile"\r\n\r\nbalanced' in body
    assert b'name="input"; filename="two_columns.pdf"' in body
    assert "prefer" not in parse.headers


def test_writes_result_and_manifest_without_the_key(tmp_path):
    vendor = Vendor(result=_result(ELEMENTS), headers={"x-model-version": "m-7", "set-cookie": "s=1"})
    target = _record(vendor, tmp_path)

    result = json.loads((target / "result.json").read_text(encoding="utf-8"))
    assert result["elements"][1]["text"] == "Left column one opens."
    manifest = json.loads((target / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["endpoint"] == "POST https://transform.vendor.test/api/v2/parse"
    assert manifest["options"] == {
        "output": "elements", "profile": "balanced", "include": ["coordinates", "table_html"],
    }
    assert manifest["http_status"] == 200
    assert manifest["response_headers"]["x-model-version"] == "m-7"
    assert "set-cookie" not in manifest["response_headers"]
    assert manifest["job_id"] == "job-1"
    assert manifest["latency_seconds"] >= 0
    assert "test-key" not in (target / "manifest.json").read_text(encoding="utf-8")


def test_follows_a_202_location_until_the_job_completes(tmp_path):
    vendor = Vendor(result=_result(ELEMENTS), accept=True, statuses=("processing", "completed"))
    target = _record(vendor, tmp_path)

    manifest = json.loads((target / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["http_status"] == 202
    assert manifest["location"] == "/api/v2/jobs/job-1"
    assert manifest["polls"] == 2
    result = json.loads((target / "result.json").read_text(encoding="utf-8"))
    assert [e["text"] for e in result["elements"]][:1] == ["Two column study"]
    poll = vendor.requests[-3]
    assert poll.url.params.get("output") == "elements"
    assert poll.url.params.get_list("include") == ["coordinates", "table_html"]


def test_deletes_the_upload_and_the_job_on_success(tmp_path):
    vendor = Vendor(result=_result(ELEMENTS))
    _record(vendor, tmp_path)
    assert vendor.deleted == ["upload/file-1", "jobs/job-1"]


def test_deletes_the_upload_when_the_job_fails(tmp_path):
    vendor = Vendor(result=_result(ELEMENTS), accept=True, statuses=("failed",))
    with pytest.raises(RecordingFailed, match="failed"):
        _record(vendor, tmp_path)
    assert vendor.deleted == ["upload/file-1", "jobs/job-1"]
    assert not (tmp_path / "two_columns").exists()


def test_a_refused_parse_is_reported(tmp_path):
    vendor = Vendor(result=_result(ELEMENTS), parse_response=httpx.Response(403, json={"code": "quota_exceeded", "message": "no"}))
    with pytest.raises(RecordingFailed, match="403"):
        _record(vendor, tmp_path)


def test_strips_signed_urls(tmp_path):
    result = _result(ELEMENTS)
    result["elements"][0]["metadata"]["image_url"] = "https://b.test/i.png?X-Amz-Signature=abc"
    result["presigned_url"] = "https://b.test/r"
    target = _record(Vendor(result=result), tmp_path)
    text = (target / "result.json").read_text(encoding="utf-8")
    assert "Signature" not in text
    assert "presigned_url" not in text


def test_measure_counts_types_and_coordinate_share():
    elements = ELEMENTS + [
        _element("Table", "a b", html="<table><tr><td>a</td></tr></table>"),
        _element("Image", ""),
        _element("NarrativeText", "no box", coordinates=None),
    ]
    m = measure(_result(elements, warnings=[{"code": "pages_degraded", "message": "x"}]))

    assert m["types"] == {"Title": 1, "NarrativeText": 2, "Formula": 1, "Table": 1, "Image": 1}
    # Text elements exclude Image; Formula and the boxless paragraph lack boxes.
    assert m["text_elements"] == 5
    assert m["text_elements_without_coordinates"] == 2
    assert m["coordinate_systems"] == {"PixelSpace": 4}
    assert m["tables_with_html"] == 1
    assert m["metadata_keys"] == ["coordinates", "page_number", "text_as_html"]
    assert m["warnings"] == ["pages_degraded"]
    assert m["page_count"] == 1


def test_reading_order_holds_only_when_every_phrase_follows_the_last():
    elements = [_element("NarrativeText", t) for t in ("Left one.", "Left two.", "Right one.")]
    assert reading_order_holds(elements, ("Left one", "Left two", "Right one"))
    assert not reading_order_holds(elements, ("Right one", "Left one"))
    assert not reading_order_holds(elements, ("Left one", "Missing"))


@pytest.mark.parametrize("name", ["figures", "numbered_headings", "table_across_pages", "two_columns"])
def test_committed_recordings_carry_no_urls_and_replay(name, tmp_path):
    from apps.ai.extraction.tests.unstructured_vendor import RECORDINGS

    for path in (RECORDINGS / name).iterdir():
        text = path.read_text(encoding="utf-8")
        assert "Signature" not in text and "X-Amz-" not in text
        assert "://" not in text.replace("https://transform.unstructured.io/api/v2/parse", "")
    target = _record(Vendor(name), tmp_path)
    assert json.loads((target / "result.json").read_text(encoding="utf-8"))["elements"]
