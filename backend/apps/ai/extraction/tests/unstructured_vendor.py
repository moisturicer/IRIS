"""Unstructured Transform over ``httpx.MockTransport``, answering from IR-984's recordings.

No vendor call: ``result.json`` under ``fixtures/unstructured/<name>/`` is served
back as Transform would serve it, synchronously or after a 202.
"""

import copy
import json
from typing import Optional

import httpx

from .fixtures import DIRECTORY

RECORDINGS = DIRECTORY / "unstructured"
BASE_URL = "https://transform.vendor.test"


def recording(name: str) -> dict:
    return json.loads((RECORDINGS / name / "result.json").read_text(encoding="utf-8"))


class Vendor:
    """Routes parse, job polling and the two deletes, and remembers them.

    ``accept`` answers the parse with 202 and a ``Location``; ``statuses`` are
    what successive polls report. ``parse_response`` replaces the parse answer.
    """

    def __init__(
        self,
        name: Optional[str] = None,
        *,
        result: Optional[dict] = None,
        accept: bool = False,
        statuses: tuple[str, ...] = ("completed",),
        headers: Optional[dict[str, str]] = None,
        parse_response: Optional[httpx.Response] = None,
    ):
        self.result = copy.deepcopy(result if result is not None else recording(name))
        self.accept = accept
        self.statuses = list(statuses)
        self.headers = headers or {}
        self.parse_response = parse_response
        self.requests: list[httpx.Request] = []
        self.parse_request: Optional[httpx.Request] = None
        self.deleted: list[str] = []

    def api(self) -> httpx.Client:
        return httpx.Client(
            base_url=BASE_URL, transport=httpx.MockTransport(self._handle),
            headers={"unstructured-api-key": "test-key"},
        )

    @property
    def job_id(self) -> str:
        return self.result["id"]

    @property
    def file_id(self) -> Optional[str]:
        return (self.result.get("source") or {}).get("file_id")

    def _handle(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        path, method = request.url.path, request.method
        if method == "POST" and path == "/api/v2/parse":
            self.parse_request = request
            return self._parse()
        if method == "GET" and path == f"/api/v2/jobs/{self.job_id}":
            return self._poll(request.url.params)
        if method == "DELETE" and path.startswith("/api/v2/"):
            self.deleted.append(path.removeprefix("/api/v2/"))
            return httpx.Response(204 if "upload" in path else 202)
        return httpx.Response(404, json={"code": "not_found", "message": f"unrouted {method} {path}"})

    def _parse(self) -> httpx.Response:
        if self.parse_response is not None:
            return self.parse_response
        if self.accept:
            return httpx.Response(
                202,
                headers={"Location": f"/api/v2/jobs/{self.job_id}", **self.headers},
                json={"id": self.job_id, "status": "queued", "source": self.result.get("source")},
            )
        return httpx.Response(200, headers=self.headers, json=self.result)

    def _poll(self, params: httpx.QueryParams) -> httpx.Response:
        status = self.statuses.pop(0) if len(self.statuses) > 1 else self.statuses[0]
        if status == "failed":
            body = {"status": "failed", "error": {"code": "could_not_parse", "message": "no"}, "result": None}
        elif status in ("completed", "completed_with_warnings"):
            body = {"status": status, "error": None, "result": self._projected(params)}
        else:
            body = {"status": status, "error": None, "result": None}
        return httpx.Response(200, headers=self.headers, json=body)

    def _projected(self, params: httpx.QueryParams) -> dict:
        """As recorded on 2026-11-13: without output=elements a job returns markdown only."""
        if params.get("output") == "elements":
            return self.result
        return {**self.result, "elements": [], "markdown": "(markdown projection)"}
