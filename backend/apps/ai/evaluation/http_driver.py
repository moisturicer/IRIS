"""Submitting questions to a running Ask IRIS over its public HTTP boundary (IR-550).

A burst sends every question at once with one shared monotonic clock, reads
each SSE stream to its end, and classifies what the reader finally received
(`capacity.classify_stream`). A transport error or client timeout is a
submission that did not succeed, never one that is dropped.

`sanitize_done` is what a published run file keeps of a `done` event: states,
figures and Record keys. Answer text, quotes, titles, reasoning and router
probabilities are left behind.
"""

from __future__ import annotations

import asyncio
import json
import time
from typing import Callable, Mapping, Optional, Sequence

import httpx

from .capacity import DEADLINE_MS, Submission, classify_stream
from .milestone import UNLABELLED

#: The client waits a little past the server's own deadline, so a server that
#: overruns it is observed as late rather than cut off by the client.
CLIENT_TIMEOUT_S = DEADLINE_MS / 1000 + 15

_LISTING_KEYS = ("completeness", "wording", "count", "coverage", "topic_count", "observed")


def parse_sse(text: str) -> list[tuple[str, dict]]:
    events = []
    for block in text.replace("\r\n", "\n").split("\n\n"):
        name, data = None, []
        for line in block.split("\n"):
            if line.startswith("event:"):
                name = line[6:].strip()
            elif line.startswith("data:"):
                data.append(line[5:].lstrip())
        if name and data:
            events.append((name, json.loads("\n".join(data))))
    return events


def _cache_hits(events) -> int:
    for name, data in reversed(events):
        if name == "done":
            return ((data.get("listing") or {}).get("observed") or {}).get("cache_hits", 0)
    return 0


async def _submit(client: httpx.AsyncClient, path: str, payload: dict,
                  clock: Callable[[], float], start: float):
    submitted = round((clock() - start) * 1000)
    try:
        # One bound on the whole exchange: httpx's own timeout is per read, and
        # a stream that keeps sending keepalives would never trip it.
        response = await asyncio.wait_for(client.post(path, json=payload), CLIENT_TIMEOUT_S)
        events = parse_sse(response.text) if response.status_code == 200 else []
        outcome = classify_stream(response.status_code, events)
    except (asyncio.TimeoutError, httpx.TimeoutException):
        return Submission(payload["question"], "timeout", submitted, None), []
    except httpx.HTTPError:
        return Submission(payload["question"], "failed", submitted, None), []
    final = round((clock() - start) * 1000)
    return Submission(payload["question"], outcome, submitted, final, _cache_hits(events)), events


async def submit_all(questions: Sequence[str], *, base_url: str, path: str, token: str,
                     extras: Optional[Sequence[Mapping]] = None, transport=None,
                     clock: Callable[[], float] = time.monotonic):
    """Each question's `Submission` and its events, all sent at once.

    ``extras`` gives each question its own payload fields, such as the
    ``conversation_id`` that makes it a queued run.
    """
    extras = extras or [{}] * len(questions)
    async with httpx.AsyncClient(
        base_url=base_url, transport=transport, timeout=CLIENT_TIMEOUT_S,
        headers={"Authorization": f"Bearer {token}"},
        limits=httpx.Limits(max_connections=None, max_keepalive_connections=None),
    ) as client:
        start = clock()
        return await asyncio.gather(*(
            _submit(client, path, {"question": q, **extra}, clock, start)
            for q, extra in zip(questions, extras, strict=True)))


async def burst(questions: Sequence[str], **kwargs) -> list[Submission]:
    return [submission for submission, _ in await submit_all(questions, **kwargs)]


def sanitize_done(done: Mapping, *, keys: Mapping[int, str]) -> dict:
    """States, figures and Record keys from a `done` event; no text a Record supplied."""
    clean = {"mode": done.get("mode"),
             "routing_lane": (done.get("routing") or {}).get("lane"),
             "citation_count": len(done.get("citations") or [])}
    listing = done.get("listing")
    if listing:
        kept = {k: listing[k] for k in _LISTING_KEYS if k in listing}
        if "candidates" in listing:
            kept["candidates"] = [_candidate(row, keys) for row in listing["candidates"]]
        clean["listing"] = kept
    return clean


def _candidate(row: Mapping, keys: Mapping[int, str]) -> dict:
    out = {"record_key": keys.get(row["record_id"], f"{UNLABELLED}{row['record_id']}"),
           "state": row["state"]}
    if row.get("restricted"):
        out["restricted"] = True
    return out
