"""IR-504: long research runs under the production ASGI server.

Driven through Django's real `ASGIHandler`, not the test client, because the
defects this guards against -- a stream buffered to the end, a slow run
holding up other requests -- exist only there.
"""
import asyncio
import json
import threading
from dataclasses import dataclass, field

import pytest
from django.core.handlers.asgi import ASGIHandler
from django.urls import reverse
from apps.accounts.sessions import start_session

from apps.ai.answers.citations import NO_SOURCES, GroundedAnswer
from apps.ai.answers.events import AgentStep, Done, RetrievalStarted
from apps.ai.composition import use_composition_root

from .corpus import make_user, root_with

pytestmark = [pytest.mark.db_required, pytest.mark.django_db(transaction=True)]


@dataclass
class Exchange:
    task: asyncio.Task = None
    sent: list = field(default_factory=list)
    first_body: asyncio.Event = field(default_factory=asyncio.Event)
    left: asyncio.Event = field(default_factory=asyncio.Event)

    @property
    def body(self):
        return b"".join(m.get("body", b"") for m in self.sent if m["type"] == "http.response.body")

    @property
    def status(self):
        return next(m["status"] for m in self.sent if m["type"] == "http.response.start")


def request(handler, method, path, token, body=None):
    exchange = Exchange()
    payload = json.dumps(body).encode() if body else b""
    pending = [{"type": "http.request", "body": payload, "more_body": False}]

    async def receive():
        if pending:
            return pending.pop()
        await exchange.left.wait()
        return {"type": "http.disconnect"}

    async def send(message):
        exchange.sent.append(message)
        if message["type"] == "http.response.body" and message.get("body"):
            exchange.first_body.set()

    scope = {
        "type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1", "method": method,
        "scheme": "http", "path": path, "raw_path": path.encode(), "query_string": b"",
        "root_path": "", "client": ("127.0.0.1", 50000), "server": ("testserver", 80),
        "headers": [(b"host", b"testserver"), (b"content-type", b"application/json"),
                    (b"content-length", str(len(payload)).encode()),
                    (b"authorization", b"Bearer " + token)],
    }
    exchange.task = asyncio.ensure_future(handler(scope, receive, send))
    return exchange


@pytest.fixture
def slow_research(monkeypatch):
    """Every stream reports one step, then waits as a long research run does."""
    release = threading.Event()

    class Orchestrator:
        metadata = {}

        def __init__(self, asked, *, max_sources):
            pass

        def answer_stream(self, user):
            yield RetrievalStarted()
            yield AgentStep(0, "plan", "running")
            release.wait(20)
            yield Done(GroundedAnswer(text="", citations=(), state=NO_SOURCES))

    monkeypatch.setattr("apps.ai.views.chatbot.ChatOrchestrator", Orchestrator)
    return release


def test_concurrent_research_streams_stream_and_do_not_block_other_requests(slow_research):
    token = str(start_session(make_user("asgi@cit.edu")).access_token).encode()

    async def scenario():
        handler = ASGIHandler()
        streams = [request(handler, "POST", reverse("ai-ask-stream"), token, {"question": "q"})
                   for _ in range(3)]
        try:
            # Each stream's first events reach the reader while its run is
            # still going -- Django alone would hold them until the end.
            await asyncio.wait_for(asyncio.gather(*(s.first_body.wait() for s in streams)), 10)
            other = request(handler, "GET", reverse("ai-status"), token)
            await asyncio.wait_for(other.task, 10)
            assert other.status == 200
            assert not any(s.task.done() for s in streams), [(s.status, s.body[:300]) for s in streams if s.task.done()]
        finally:
            slow_research.set()
        await asyncio.wait_for(asyncio.gather(*(s.task for s in streams)), 10)
        return streams

    with use_composition_root(root_with()):
        streams = asyncio.run(scenario())
    for stream in streams:
        body = stream.body.decode()
        assert body.index("event: agent_step") < body.index("event: done")


def test_a_reader_leaving_closes_the_run_on_its_own_thread(monkeypatch):
    token = str(start_session(make_user("leave@cit.edu")).access_token).encode()
    closed, release = threading.Event(), threading.Event()

    class Orchestrator:
        metadata = {}

        def __init__(self, asked, *, max_sources):
            pass

        def answer_stream(self, user):
            try:
                yield RetrievalStarted()
                release.wait(20)
                yield AgentStep(0, "plan", "running")
                yield Done(GroundedAnswer(text="", citations=(), state=NO_SOURCES))
            except GeneratorExit:
                closed.set()
                raise

    monkeypatch.setattr("apps.ai.views.chatbot.ChatOrchestrator", Orchestrator)

    async def scenario():
        stream = request(ASGIHandler(), "POST", reverse("ai-ask-stream"), token, {"question": "q"})
        await asyncio.wait_for(stream.first_body.wait(), 10)
        stream.left.set()
        # The handler must see the disconnect before the run can finish.
        await asyncio.wait({stream.task}, timeout=10)
        release.set()

    with use_composition_root(root_with()):
        asyncio.run(scenario())
    assert closed.wait(10)
