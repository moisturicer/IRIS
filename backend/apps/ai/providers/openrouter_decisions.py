"""OpenRouter Decisions API adapter, pinned to Jev (IR-482, ADR-036 amendment).

`POST https://openrouter.ai/api/alpha/decisions` -- the path says alpha, and it
is not the OpenAI-style chat endpoint, so `OpenAICompatibleAdapter` cannot
reach it. Evaluation only: nothing on a reader's path constructs this.

The model is pinned to a named release and the `~...-latest` alias is refused,
so a run is reproducible. The response's own `model` (the dated build actually
served) is returned for the run file.

Retention, training and rate-limit terms are **not stated** in OpenRouter's
docs for this endpoint. Unverified; see the ADR-036 amendment.
"""

from __future__ import annotations

import math
import re
from typing import Any, Mapping, Optional

import httpx

from apps.ai.providers.decisions import (
    DecisionMalformed,
    DecisionModel,
    DecisionUnavailable,
    NoulAnswer,
)
from apps.ai.providers.errors import ErrorKind, classify_status_code

DECISIONS_URL = "https://openrouter.ai/api/alpha/decisions"
PINNED_MODEL = "typesafe/jev-1.13"
QUESTION_NAME = "needs_corpus"
DEFAULT_TIMEOUT_SECONDS = 15.0
#: vendor/name-<version>: ends in a version number, so no alias matches.
_PINNED = re.compile(r"[\w.]+/[\w.]+-\d[\w.]*")


def _kind_for_status(status: int, message: str) -> ErrorKind:
    if status == 402:
        return ErrorKind.AUTH  # out of credits: a configuration problem
    if status == 524:
        return ErrorKind.TIMEOUT
    if status == 413:
        return ErrorKind.CONTEXT_OVERFLOW
    return classify_status_code(status, None, message)


class OpenRouterDecisionsAdapter(DecisionModel):
    def __init__(
        self,
        api_key: str,
        *,
        model: str = PINNED_MODEL,
        client: Optional[httpx.Client] = None,
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
    ) -> None:
        if not (api_key or "").strip():
            raise ValueError("an OpenRouter API key is required.")
        if not _PINNED.fullmatch(model or ""):
            raise ValueError(
                f"{model!r} is not a pinned model; pin a release such as "
                f"{PINNED_MODEL!r}, never an alias."
            )
        self._api_key = api_key.strip()
        self._model = model
        self._client = client
        self._timeout = timeout_seconds

    @property
    def model(self) -> str:
        return self._model

    def noul(
        self,
        state: Any,
        *,
        instructions: str,
        criteria: Mapping[str, str],
        timeout_seconds: Optional[float] = None,
    ) -> NoulAnswer:
        payload = {
            "model": self._model,
            "state": state,
            "questions": {
                QUESTION_NAME: {
                    "type": "noul",
                    "instructions": instructions,
                    "criteria": dict(criteria),
                }
            },
        }
        timeout = timeout_seconds or self._timeout
        try:
            response = self._post(payload, timeout)
        except httpx.TimeoutException as exc:
            raise DecisionUnavailable("decision call timed out", ErrorKind.TIMEOUT) from exc
        except httpx.HTTPError as exc:
            raise DecisionUnavailable(
                f"decision call failed: {type(exc).__name__}", ErrorKind.NETWORK
            ) from exc

        if response.status_code >= 400:
            raise DecisionUnavailable(
                f"decisions endpoint returned {response.status_code}",
                _kind_for_status(response.status_code, ""),
            )
        return self._parse(response)

    def _post(self, payload: dict, timeout: float) -> httpx.Response:
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        if self._client is not None:
            return self._client.post(
                DECISIONS_URL, json=payload, headers=headers, timeout=timeout
            )
        with httpx.Client() as client:
            return client.post(
                DECISIONS_URL, json=payload, headers=headers, timeout=timeout
            )

    @staticmethod
    def _parse(response: httpx.Response) -> NoulAnswer:
        try:
            body = response.json()
        except ValueError as exc:
            raise DecisionMalformed("response body is not JSON") from exc
        if not isinstance(body, dict) or not isinstance(body.get("answers"), dict):
            raise DecisionMalformed("response has no answers object")
        answer = body["answers"].get(QUESTION_NAME)
        if not isinstance(answer, dict) or answer.get("type") != "noul":
            raise DecisionMalformed("answer is not a noul answer")
        value = answer.get("noul")
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(value)
            or not 0 <= value <= 1
        ):
            raise DecisionMalformed("noul is not a probability")

        usage = body.get("usage") if isinstance(body.get("usage"), dict) else {}
        tokens = usage.get("input_tokens")
        cost = usage.get("cost")
        return NoulAnswer(
            probability=float(value),
            model=str(body.get("model") or ""),
            input_tokens=tokens if isinstance(tokens, int) and not isinstance(tokens, bool) else None,
            cost_usd=float(cost) if isinstance(cost, (int, float)) and not isinstance(cost, bool) else None,
        )
