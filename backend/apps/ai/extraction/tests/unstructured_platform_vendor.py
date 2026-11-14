"""Unstructured's Platform partition endpoint over ``httpx.MockTransport`` (IR-985).

Answers from ``fixtures/unstructured_platform/<name>/``, with the recorded
status and page header. ``answers`` replaces successive answers: an
``httpx.Response`` or an exception the transport raises.
"""

import copy
import json
from typing import Union

import httpx

from .fixtures import DIRECTORY

RECORDINGS = DIRECTORY / "unstructured_platform"
BASE_URL = "https://api.unstructuredapp.io"
API_KEY = "test-platform-key"

Answer = Union[httpx.Response, Exception]


def recording(name: str):
    return json.loads((RECORDINGS / name / "result.json").read_text(encoding="utf-8"))


def manifest(name: str) -> dict:
    return json.loads((RECORDINGS / name / "manifest.json").read_text(encoding="utf-8"))


class Vendor:
    def __init__(self, name: str = "two_columns", *, result=None, answers: tuple[Answer, ...] = ()):
        recorded = manifest(name)
        self.result = copy.deepcopy(result if result is not None else recording(name))
        self.status = recorded["http_status"]
        self.pages = recorded["response_headers"].get("x-num-pages")
        self.answers = list(answers)
        self.requests: list[httpx.Request] = []

    def api(self) -> httpx.Client:
        return httpx.Client(base_url=BASE_URL, transport=httpx.MockTransport(self._handle),
                            headers={"unstructured-api-key": API_KEY})

    def _handle(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if request.method != "POST" or request.url.path != "/general/v0/general":
            return httpx.Response(404, json={"detail": "Not Found"})
        if self.answers:
            answer = self.answers.pop(0)
            if isinstance(answer, Exception):
                raise answer
            return answer
        headers = {"x-num-pages": self.pages} if self.pages else {}
        return httpx.Response(self.status, headers=headers, json=self.result)

    def form(self, index: int = -1) -> bytes:
        return self.requests[index].read()
