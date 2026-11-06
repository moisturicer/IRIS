"""The LlamaParse re-record script (IR-849).

Driven through an ``httpx.MockTransport`` that plays LlamaParse, so the
request is really built and the files are really written. No vendor call.
"""

import json

import httpx
import pytest

from apps.ai.extraction.tests.fixtures.record_llamaparse import (
    RecordingFailed,
    record,
)

API = "https://api.example.test"
PDF = b"%PDF-1.4 synthetic"
VERSION = "2026-09-28"


class FakeLlamaParse:
    """Answers the five calls the script makes, and remembers them."""

    def __init__(self, statuses=("COMPLETED",), credits=(18.0,)):
        self.statuses = list(statuses)
        self.credits = list(credits)
        self.requests: list[httpx.Request] = []
        self.parse_body: dict | None = None
        self.deleted: list[str] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        path, method = request.url.path, request.method
        if method == "POST" and path == "/api/v1/beta/files":
            return httpx.Response(200, json={"id": "dfl-1", "name": "figures.pdf"})
        if method == "POST" and path == "/api/v2/parse":
            self.parse_body = json.loads(request.content)
            return httpx.Response(200, json={"id": "pjb-1", "status": "PENDING"})
        if method == "GET" and path == "/api/v2/parse/pjb-1":
            status = self.statuses.pop(0) if len(self.statuses) > 1 else self.statuses[0]
            if "expand" not in request.url.params:
                return httpx.Response(200, json={"job": {"id": "pjb-1", "status": status}})
            credits = self.credits.pop(0) if len(self.credits) > 1 else self.credits[0]
            return httpx.Response(200, json=_result(status, credits))
        if method == "DELETE" and path == "/api/v1/beta/files/dfl-1":
            self.deleted.append("dfl-1")
            return httpx.Response(200, json={})
        if request.url.host == "bucket.test":
            if path.endswith(".jsonl"):
                return httpx.Response(200, content=b'{"page_number": 1, "success": true}\n')
            return httpx.Response(200, content=b"\x89PNG figure")
        return httpx.Response(404)


def _result(status, credits):
    return {
        "job": {"id": "pjb-1", "status": status, "usage": {"credits": credits}},
        "items": {"pages": [{"page_number": 1, "items": [{"type": "heading", "level": 1}]}]},
        "metadata": {"pages": [{"page_number": 1, "confidence": 0.9}], "document": {}},
        "images_content_metadata": {
            "total_count": 1,
            "images": [
                {
                    "index": 0,
                    "filename": "image_0.png",
                    "category": "layout",
                    "presigned_url": "https://bucket.test/image_0.png?X-Amz-Signature=s",
                }
            ],
        },
        "result_content_metadata": {
            "grounded_items": {"presigned_url": "https://bucket.test/grounded.jsonl?X-Amz-Signature=s"}
        },
    }


def _clients(fake):
    transport = httpx.MockTransport(fake)
    api = httpx.Client(base_url=API, transport=transport, headers={"Authorization": "Bearer k"})
    return api, httpx.Client(transport=transport)


def _record(fake, tmp_path, **kwargs):
    api, downloads = _clients(fake)
    return record(
        "figures", PDF, tmp_path, api=api, downloads=downloads, version=VERSION,
        sleep=lambda _: None, **kwargs,
    )


def test_a_recording_sends_adr_056s_request_and_deletes_the_upload(tmp_path):
    fake = FakeLlamaParse()

    _record(fake, tmp_path)

    assert fake.parse_body == {
        "file_id": "dfl-1",
        "tier": "agentic",
        "version": VERSION,
        "disable_cache": True,
        "processing_options": {
            "cost_optimizer": {"enable": True},
            "specialized_chart_parsing": "agentic",
        },
        "output_options": {
            "granular_bboxes": ["word", "line", "cell"],
            "extract_printed_page_number": True,
            "markdown": {"tables": {"merge_continued_tables": True}},
            "images_to_save": ["layout"],
        },
    }
    assert fake.deleted == ["dfl-1"]


def test_a_failed_job_still_deletes_the_upload(tmp_path):
    fake = FakeLlamaParse(statuses=("FAILED",))

    with pytest.raises(RecordingFailed, match="FAILED"):
        _record(fake, tmp_path)

    assert fake.deleted == ["dfl-1"]
    assert not (tmp_path / "figures").exists()


def test_a_recording_commits_result_grounding_images_and_manifest(tmp_path):
    target = _record(FakeLlamaParse(), tmp_path)

    result = json.loads((target / "result.json").read_text(encoding="utf-8"))
    assert result["items"]["pages"][0]["items"] == [{"type": "heading", "level": 1}]
    assert result["job"]["usage"] == {"credits": 18.0}
    assert (target / "images" / "image_0.png").read_bytes() == b"\x89PNG figure"
    assert (target / "grounded_items.jsonl").read_bytes().startswith(b'{"page_number": 1')

    manifest = json.loads((target / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["tier"] == "agentic"
    assert manifest["version"] == VERSION
    assert manifest["request"]["disable_cache"] is True
    assert manifest["credits"] == 18.0


def test_nothing_committed_carries_a_signed_url_or_the_key(tmp_path):
    target = _record(FakeLlamaParse(), tmp_path)

    for path in target.rglob("*.json"):
        text = path.read_text(encoding="utf-8")
        assert "X-Amz-Signature" not in text
        assert "Bearer" not in text


def test_downloads_never_carry_the_api_key(tmp_path):
    fake = FakeLlamaParse()

    _record(fake, tmp_path)

    signed = [r for r in fake.requests if r.url.host == "bucket.test"]
    assert len(signed) == 2
    assert all("authorization" not in r.headers for r in signed)


def test_it_polls_until_the_job_completes_and_waits_for_credits(tmp_path):
    fake = FakeLlamaParse(statuses=("PENDING", "RUNNING", "COMPLETED"), credits=(None, 18.0))

    target = _record(fake, tmp_path)

    polls = [
        r for r in fake.requests
        if r.url.path == "/api/v2/parse/pjb-1" and "expand" not in r.url.params
    ]
    assert len(polls) == 3
    assert json.loads((target / "manifest.json").read_text())["credits"] == 18.0


def test_latest_is_refused_before_anything_is_sent(tmp_path):
    fake = FakeLlamaParse()
    api, downloads = _clients(fake)

    with pytest.raises(RecordingFailed, match="latest"):
        record("figures", PDF, tmp_path, api=api, downloads=downloads, version="latest")

    assert fake.requests == []


def test_a_null_usage_records_unknown_credits_rather_than_failing(tmp_path):
    fake = FakeLlamaParse()
    respond = fake.__call__

    def usage_null(request):
        response = respond(request)
        if "expand" in request.url.params:
            body = response.json()
            body["job"]["usage"] = None
            return httpx.Response(200, json=body)
        return response

    api, downloads = _clients(usage_null)
    target = record(
        "figures", PDF, tmp_path, api=api, downloads=downloads, version=VERSION,
        sleep=lambda _: None,
    )

    assert json.loads((target / "manifest.json").read_text())["credits"] is None
    assert fake.deleted == ["dfl-1"]


def _refusing_delete(fake):
    def handler(request):
        if request.method == "DELETE":
            return httpx.Response(500, text="nope")
        return fake(request)

    return handler


def test_a_refused_delete_fails_the_recording(tmp_path):
    api, downloads = _clients(_refusing_delete(FakeLlamaParse()))

    with pytest.raises(RecordingFailed, match="may remain"):
        record("figures", PDF, tmp_path, api=api, downloads=downloads, sleep=lambda _: None)


def test_a_refused_delete_does_not_hide_the_jobs_own_failure(tmp_path):
    api, downloads = _clients(_refusing_delete(FakeLlamaParse(statuses=("FAILED",))))

    with pytest.raises(RecordingFailed, match="ended FAILED"):
        record("figures", PDF, tmp_path, api=api, downloads=downloads, sleep=lambda _: None)
