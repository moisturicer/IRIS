"""LlamaExtract over ``httpx.MockTransport``, answering with AUTHORED payloads.

**Not a recording.** No LlamaExtract output has been recorded yet (IR-846):
these payloads are written from the v2 response format LlamaIndex documents
(``/llamaparse/extract/guides/response-format``, read 2026-11-03), shaped to
the synthetic ``two_columns`` fixture so the cited text can be found in its
recorded parse. Replace them with a recording once one exists.
"""

import copy
import json
from typing import Optional

import httpx

BASE_URL = "https://api.vendor.test"
JOB_ID = "ext-authored"
PARSE_JOB_ID = "pjb-urh3sj10fnjq75l9xitead6vs9lf"  # two_columns' recorded parse


def two_columns_reading() -> dict:
    """What a completed job returns with ``expand=extract_metadata,usage``."""
    return {
        "id": JOB_ID,
        "status": "COMPLETED",
        "file_input": PARSE_JOB_ID,
        "error_message": None,
        "extract_result": {
            "title": "Two column study",
            "authors": ["Ana Cruz", "Ben Reyes"],
            "abstract": "Left column one opens. Right column one resumes.",
            "keywords": ["columns", "reading order"],
            "publication_year": 2026,
        },
        "extract_metadata": {
            "field_metadata": {
                "document_metadata": {
                    "title": {"citation": [{"page": 1, "matching_text": "Two column study"}], "confidence": 0.97},
                    "authors": {"citation": [{"page": 1, "matching_text": "Ana Cruz and Ben Reyes"}], "confidence": 0.62},
                    "abstract": {
                        "citation": [{"page": 1, "matching_text": "Left column one opens. Right column one resumes."}],
                        "confidence": 0.91,
                    },
                    "keywords": {"citation": [], "confidence": 0.4},
                    "publication_year": {"citation": [{"page": 1, "matching_text": "2026"}]},
                },
            },
            "parse_job_id": PARSE_JOB_ID,
            "parse_tier": "agentic",
        },
        "usage": {"credits": 15.0, "extract_credits": 15.0, "parse_credits": None},
    }


class Vendor:
    """Routes create, poll and fetch, and remembers them.

    ``statuses`` are what successive polls report before the result fetch.
    ``failure`` replaces a step's answer: ``(step, response_or_exception)``.
    """

    def __init__(
        self,
        *,
        reading: Optional[dict] = None,
        statuses: tuple[str, ...] = ("RUNNING", "COMPLETED"),
        error_message: Optional[str] = None,
        failure: Optional[tuple[str, object]] = None,
    ):
        self.reading = copy.deepcopy(reading if reading is not None else two_columns_reading())
        self.statuses = list(statuses)
        self.error_message = error_message
        self.failure = failure
        self.requests: list[httpx.Request] = []
        self.created: Optional[dict] = None

    def api(self) -> httpx.Client:
        return httpx.Client(base_url=BASE_URL, transport=httpx.MockTransport(self._route))

    def _fail(self, step):
        if self.failure and self.failure[0] == step:
            answer = self.failure[1]
            if isinstance(answer, Exception):
                raise answer
            return answer
        return None

    def _route(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        path = request.url.path
        if request.method == "POST" and path == "/api/v2/extract":
            if (failed := self._fail("create")) is not None:
                return failed
            self.created = json.loads(request.content)
            return httpx.Response(200, json={"id": JOB_ID, "status": "PENDING"})
        if request.method == "GET" and path == f"/api/v2/extract/{JOB_ID}":
            if request.url.params.get_list("expand"):
                if (failed := self._fail("fetch")) is not None:
                    return failed
                return httpx.Response(200, json=self.reading)
            if (failed := self._fail("poll")) is not None:
                return failed
            status = self.statuses.pop(0) if len(self.statuses) > 1 else self.statuses[0]
            return httpx.Response(200, json={
                "id": JOB_ID, "status": status, "error_message": self.error_message,
            })
        return httpx.Response(404, json={"detail": f"no route {request.method} {path}"})
