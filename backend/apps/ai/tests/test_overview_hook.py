"""The one-sentence hook generated with the AI Overview (IR-604).

Discover's one-column card shows a short hook apart from the abstract. It is
written in the same completion as the Overview, so the whole paper is sent
once, stored on the same row, and served on the record payloads.
"""

import pytest

from apps.ai.composition import CompositionRoot, use_composition_root
from apps.ai.models import ChunkSet, DocumentChunk, RecordOverview
from apps.ai.overview import PROMPT_VERSION, overview_for
from apps.ai.overview.hook import HOOK_MAX_CHARS, split_hook
from apps.ai.overview.service import generate_overview
from apps.ai.providers.fakes import ScriptedLLM
from apps.records.models import Record
from core.enums import PipelineStatus

from .corpus import make_user

pytestmark = [pytest.mark.db_required, pytest.mark.django_db]

HOOK = "Turns Metro Cebu's food waste into power, cutting landfill use by an estimated 30%."


@pytest.fixture(autouse=True)
def suppress_task_publish(monkeypatch):
    monkeypatch.setattr("apps.ai.overview.service._enqueue_overview", lambda *args: None)


def _root(llm, permits=lambda record: True):
    return CompositionRoot(llm=llm, permits=permits)


def _record(status=PipelineStatus.PUBLISHED, title="Waste to Energy"):
    record = Record.objects.create(
        title=title, abstract="This thesis studies things. It also does more.",
        pipeline_status=status,
    )
    chunk_set = ChunkSet.objects.create(
        record=record, extraction_hash="e", strategy_id="s", options={},
        content_hash="h", is_active=True,
    )
    DocumentChunk.objects.create(
        chunk_set=chunk_set, record=record, sequence=0, max_sequence=0,
        text="Food waste digestion.", content="Food waste digestion.",
        context_path=["Paper"], token_count=3, text_hash="t0",
        source_page=1, element_kinds=["paragraph"],
    )
    return record


def _generate(record, reply):
    llm = ScriptedLLM(reply=reply)
    chunk_set = ChunkSet.objects.get(record=record, is_active=True)
    with use_composition_root(_root(llm)):
        assert overview_for(record)["state"] == "generating"
        generate_overview(record.pk, chunk_set.pk, chunk_set.content_hash, PROMPT_VERSION)
    return llm


class SplitHookTests:
    def test_the_hook_line_is_taken_off_the_end(self):
        body, hook = split_hook(f"An account [p. 1].\n\nHOOK: {HOOK}")

        assert body == "An account [p. 1]."
        assert hook == HOOK

    def test_a_reply_with_no_hook_line_has_no_hook(self):
        assert split_hook("An account [p. 1].") == ("An account [p. 1].", "")

    def test_a_hook_over_the_limit_is_dropped_not_cut(self):
        too_long = "word " * 40
        assert len(too_long.strip()) > HOOK_MAX_CHARS

        body, hook = split_hook(f"An account.\nHOOK: {too_long}")

        assert body == "An account."
        assert hook == ""

    def test_a_hook_at_the_limit_is_kept(self):
        exact = "x" * HOOK_MAX_CHARS
        assert split_hook(f"An account.\nHOOK: {exact}")[1] == exact

    def test_citation_markers_and_markdown_are_not_part_of_a_hook(self):
        _body, hook = split_hook("An account.\nHOOK: **Cuts** landfill use [p. 4] by 30%.")

        assert hook == "Cuts landfill use by 30%."

    def test_symbols_that_belong_to_the_claim_are_kept(self):
        _body, hook = split_hook("An account.\nHOOK: Cuts cost by >30% and ranks #1 in snake_case tests.")

        assert hook == "Cuts cost by >30% and ranks #1 in snake_case tests."

    def test_a_blank_hook_line_is_no_hook(self):
        assert split_hook("An account.\nHOOK:   ") == ("An account.", "")


class GenerationTests:
    def test_one_completion_yields_the_overview_and_its_hook(self):
        record = _record()

        llm = _generate(record, f"An account [p. 1].\n\nHOOK: {HOOK}")

        assert len(llm.calls) == 1
        stored = RecordOverview.objects.get(record=record)
        assert stored.state == "ready"
        assert stored.hook == HOOK
        assert "HOOK" not in stored.text
        assert HOOK not in stored.text

    def test_the_prompt_asks_for_a_hook_grounded_in_the_paper(self):
        llm = _generate(_record(), "An account [p. 1].")

        [(_system, user)] = llm.calls
        assert "HOOK:" in user
        assert str(HOOK_MAX_CHARS) in user

    def test_no_hook_line_leaves_the_overview_ready_and_the_hook_empty(self):
        record = _record()

        _generate(record, "An account [p. 1].")

        stored = RecordOverview.objects.get(record=record)
        assert stored.state == "ready"
        assert stored.hook == ""

    def test_an_over_long_hook_is_not_stored(self):
        record = _record()

        _generate(record, f"An account [p. 1].\nHOOK: {'word ' * 60}")

        assert RecordOverview.objects.get(record=record).hook == ""

    def test_regeneration_clears_the_previous_hook_until_the_new_one_lands(self):
        record = _record()
        RecordOverview.objects.create(
            record=record, text="Old.", content_hash="old-hash", hook="Old hook.",
            prompt_version=PROMPT_VERSION, state="ready",
        )

        with use_composition_root(_root(ScriptedLLM())):
            assert overview_for(record)["state"] == "generating"

        assert RecordOverview.objects.get(record=record).hook == ""

    def test_the_overview_wire_shape_does_not_carry_the_hook_marker(self):
        record = _record()

        _generate(record, f"An account [p. 1].\nHOOK: {HOOK}")

        with use_composition_root(_root(ScriptedLLM())):
            result = overview_for(record)
        assert "HOOK" not in result["overview"]["text"]


def _ready(record, hook=HOOK, **extra):
    fields = dict(
        text="An account.", content_hash="h", hook=hook,
        prompt_version=PROMPT_VERSION, state="ready",
    )
    fields.update(extra)
    return RecordOverview.objects.create(record=record, **fields)


def _listed(client, record):
    response = client.get("/api/v1/records/")
    assert response.status_code == 200
    body = response.json()
    rows = body["results"] if isinstance(body, dict) else body
    return {row["id"]: row for row in rows}.get(record.pk)


@pytest.fixture
def reader(client_for):
    return client_for(make_user("reader@cit.edu"))


@pytest.fixture(autouse=True)
def gate_open():
    with use_composition_root(_root(ScriptedLLM())):
        yield


class ServedOnTheRecordListTests:
    def test_the_list_row_carries_the_stored_hook(self, reader):
        record = _record()
        _ready(record)

        assert _listed(reader, record)["ai_hook"] == HOOK

    def test_a_record_with_no_overview_has_no_hook(self, reader):
        record = _record()

        assert _listed(reader, record)["ai_hook"] is None

    def test_a_hook_that_was_never_written_is_no_hook(self, reader):
        record = _record()
        _ready(record, hook="")

        assert _listed(reader, record)["ai_hook"] is None

    @pytest.mark.parametrize("state", ["generating", "unavailable"])
    def test_an_overview_that_is_not_ready_has_no_hook(self, reader, state):
        record = _record()
        _ready(record, state=state)

        assert _listed(reader, record)["ai_hook"] is None

    def test_a_hook_from_an_older_prompt_version_is_not_served(self, reader):
        record = _record()
        _ready(record, prompt_version=PROMPT_VERSION - 1)

        assert _listed(reader, record)["ai_hook"] is None

    def test_a_record_the_disclosure_gate_refuses_serves_no_hook(self, reader):
        record = _record()
        _ready(record)

        with use_composition_root(_root(ScriptedLLM(), permits=lambda r: False)):
            assert _listed(reader, record)["ai_hook"] is None

    @pytest.mark.parametrize("path", ["/api/v1/records/", "/api/v1/records/for-you/"])
    def test_queries_do_not_grow_with_the_number_of_cards(self, client_for, path):
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        # A fresh reader each time: the feed keeps a per-reader snapshot.
        def count(email):
            client = client_for(make_user(email))
            with CaptureQueriesContext(connection) as queries:
                response = client.get(path)
            assert response.status_code == 200
            return len(queries)

        _ready(_record(title="Paper 0"))
        one = count("first@cit.edu")
        for i in range(1, 6):
            _ready(_record(title=f"Paper {i}"))

        assert count("second@cit.edu") == one


class HiddenRecordTests:
    def test_a_draft_the_reader_cannot_see_exposes_no_hook(self, reader):
        draft = _record(status=PipelineStatus.DRAFT, title="Private draft")
        _ready(draft)

        assert _listed(reader, draft) is None
        detail = reader.get(f"/api/v1/records/{draft.pk}/")
        assert detail.status_code == 404
        assert HOOK not in detail.content.decode()

    def test_detail_carries_the_hook_for_a_record_the_reader_may_read(self, reader):
        record = _record()
        _ready(record)

        detail = reader.get(f"/api/v1/records/{record.pk}/")

        assert detail.json()["ai_hook"] == HOOK
