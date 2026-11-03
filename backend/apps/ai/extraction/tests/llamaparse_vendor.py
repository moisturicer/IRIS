"""LlamaParse over ``httpx.MockTransport``, answering from IR-849's recordings.

No vendor call: the recorded ``result.json`` and ``grounded_items.jsonl`` are
served back with presigned URLs restored, so the adapter downloads them as it
would in production.
"""

import copy
import json
from pathlib import Path
from typing import Optional

import httpx

from .fixtures import DIRECTORY

RECORDINGS = DIRECTORY / "llamaparse"
BASE_URL = "https://api.vendor.test"
DOWNLOADS = "https://downloads.vendor.test"
FILE_ID = "dfl-recorded"


def recording(name: str) -> dict:
    return json.loads((RECORDINGS / name / "result.json").read_text(encoding="utf-8"))


def grounded(name: str) -> bytes:
    return (RECORDINGS / name / "grounded_items.jsonl").read_bytes()


class Vendor:
    """Routes the four calls the adapter makes, and remembers them.

    ``statuses`` are what successive polls report. ``failure`` replaces a
    route's answer: ``(step, response_or_exception)`` with step one of
    ``upload``, ``create``, ``poll``, ``fetch``, ``download``, ``delete``.
    """

    def __init__(
        self,
        name: Optional[str] = None,
        *,
        result: Optional[dict] = None,
        statuses: tuple[str, ...] = ("RUNNING", "COMPLETED"),
        error_message: Optional[str] = None,
        failure: Optional[tuple[str, object]] = None,
        images: Optional[dict[str, bytes]] = None,
        credits_after: int = 0,
    ):
        self.result = copy.deepcopy(result if result is not None else recording(name))
        self.grounded = grounded(name) if name else b""
        self.statuses = list(statuses)
        self.error_message = error_message
        self.failure = failure
        self.images = images or {}
        self.credits_after = credits_after
        self.requests: list[httpx.Request] = []
        self.created: Optional[dict] = None
        self.deleted: list[str] = []
        self.fetches = 0

    # -- clients ----------------------------------------------------------

    def api(self) -> httpx.Client:
        return httpx.Client(
            base_url=BASE_URL, transport=httpx.MockTransport(self._handle),
            headers={"Authorization": "Bearer test-key"},
        )

    def downloads(self) -> httpx.Client:
        return httpx.Client(transport=httpx.MockTransport(self._handle))

    # -- routing ----------------------------------------------------------

    def _fail(self, step: str) -> Optional[httpx.Response]:
        if not self.failure or self.failure[0] != step:
            return None
        answer = self.failure[1]
        if isinstance(answer, BaseException):
            raise answer
        if callable(answer):
            return answer()
        return answer

    def _handle(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        path, method = request.url.path, request.method
        if request.url.host == "downloads.vendor.test":
            return self._fail("download") or self._download(path)
        if method == "POST" and path == "/api/v1/beta/files":
            return self._fail("upload") or httpx.Response(200, json={"id": FILE_ID})
        if method == "DELETE" and path == f"/api/v1/beta/files/{FILE_ID}":
            self.deleted.append(FILE_ID)
            return self._fail("delete") or httpx.Response(204)
        if method == "POST" and path == "/api/v2/parse":
            self.created = json.loads(request.content)
            return self._fail("create") or httpx.Response(200, json={"id": self.result["job"]["id"]})
        if method == "GET" and path == f"/api/v2/parse/{self.result['job']['id']}":
            if "expand" in request.url.params:
                return self._fail("fetch") or self._result()
            return self._fail("poll") or self._poll()
        return httpx.Response(404, json={"detail": f"unrouted {method} {path}"})

    def _poll(self) -> httpx.Response:
        status = self.statuses.pop(0) if len(self.statuses) > 1 else self.statuses[0]
        job = {**self.result["job"], "status": status, "usage": None}
        if status == "FAILED":
            job["error_message"] = self.error_message
        return httpx.Response(200, json={"job": job})

    def _result(self) -> httpx.Response:
        self.fetches += 1
        body = copy.deepcopy(self.result)
        if self.fetches <= self.credits_after:
            body["job"]["usage"] = {"credits": None}
        metadata = body.get("result_content_metadata") or {}
        if (metadata.get("grounded_items") or {}).get("exists"):
            metadata["grounded_items"]["presigned_url"] = f"{DOWNLOADS}/grounded_items.jsonl"
        for image in (body.get("images_content_metadata") or {}).get("images", []):
            image["presigned_url"] = f"{DOWNLOADS}/images/{image['filename']}"
        return httpx.Response(200, json=body)

    def _download(self, path: str) -> httpx.Response:
        if path == "/grounded_items.jsonl":
            return httpx.Response(200, content=self.grounded)
        name = Path(path).name
        if name in self.images:
            return httpx.Response(200, content=self.images[name])
        return httpx.Response(404)


def no_sleep(_: float) -> None:
    pass
