"""Conversation state: what the reader saw, revisioned per delivered Turn (IR-592).

Spec §4 of the 2026-10-15 general-tools specification; acceptance scenarios
A01-A03, A08, A11 and A12. The concurrency tests use real transactions,
because a revision check that only holds inside one test transaction proves
nothing about two workers.
"""

import threading

import pytest
from django.db import connection

from apps.ai.answers.citations import GENERATED, PARTIAL, UNAVAILABLE, Citation, GroundedAnswer
from apps.ai.conversation_state import (
    CONFLICT,
    RECONSTRUCTED,
    RECORDED,
    ContextState,
    conversation_context,
    reissue_handles,
    snapshot,
)
from apps.ai.conversations import record_turn
from apps.ai.history import readable_turns, recent_window
from apps.ai.memory import ConversationMemory
from apps.ai.models import (
    TURN_QUESTION_VECTOR,
    ChunkSet,
    Conversation,
    ConversationState,
    Turn,
    TurnEmbedding,
)
from apps.records.models import Record
from core.enums import PipelineStatus

from .corpus import make_user

pytestmark = [pytest.mark.db_required]


def _record(title, content_hash=None):
    record = Record.objects.create(
        title=title, abstract=f"About {title}.", pipeline_status=PipelineStatus.PUBLISHED
    )
    if content_hash:
        ChunkSet.objects.create(
            record=record, extraction_hash=f"e{title}", strategy_id="s", options={},
            content_hash=content_hash, is_active=True, page_sizes={},
        )
    return record


def _citation(marker, record):
    return Citation(
        marker=marker, record_id=record.pk, record_title=record.title,
        chunk_id=None, source_page=None, text="", context_path=(),
    )


def _answer(*records, state=GENERATED, text="An answer."):
    return GroundedAnswer(
        text=text,
        citations=tuple(_citation(i, r) for i, r in enumerate(records, start=1)),
        degraded=False,
        state=state,
    )


def _listing(*records):
    return {"completeness": "complete", "records": [{"record_id": r.pk} for r in records]}


def _revoke(record):
    Record.objects.filter(pk=record.pk).update(pipeline_status=PipelineStatus.DRAFT)


@pytest.fixture
def reader(db):
    return make_user("reader@cit.edu")


@pytest.fixture
def conversation(reader):
    return Conversation.objects.create(user=reader)


@pytest.mark.django_db
class TransitionTests:
    def test_a_topic_change_drops_choices_made_under_the_old_topic(self):
        state = ContextState(topic="MeshKV", presented=(1, 2), selected=(1, 2), excluded=(3,))

        changed = state.with_topic("federated learning")

        assert changed.topic == "federated learning"
        assert changed.selected == () and changed.excluded == ()
        assert changed.presented == (1, 2)

    def test_restating_the_same_topic_keeps_the_selection(self):
        state = ContextState(topic="MeshKV", presented=(1, 2), selected=(1, 2))

        assert state.with_topic("meshkv").selected == (1, 2)

    def test_find_another_excludes_everything_already_shown(self):
        state = ContextState(presented=(1, 2), excluded=(7,)).find_another()

        assert state.excluded == (7, 1, 2)

    def test_compare_those_two_selects_from_what_was_shown(self):
        state = ContextState(presented=(4, 5, 6)).selecting_ordinals(1, 3)

        assert state.selected == (4, 6)

    def test_an_ordinal_beyond_what_was_shown_selects_nothing(self):
        with pytest.raises(ValueError):
            ContextState(presented=(4, 5)).selecting_ordinals(3)

    def test_a_selection_must_come_from_what_was_shown(self):
        with pytest.raises(ValueError):
            ContextState(presented=(4, 5)).selecting((9,))

    def test_showing_new_papers_resolves_a_pending_clarification(self):
        state = ContextState().clarifying("Which MeshKV paper?", (1, 2))

        assert state.pending_clarification == {"question": "Which MeshKV paper?", "options": [1, 2]}
        assert state.presenting((1,)).pending_clarification is None

    def test_the_request_and_the_retrieval_query_are_kept_apart(self):
        state = ContextState().asked("simplify that", "simplify MeshKV consistency")

        assert state.request == "simplify that"
        assert state.retrieval_query == "simplify MeshKV consistency"


@pytest.mark.django_db
class DeliveredTurnTests:
    def test_a_delivered_listing_records_the_order_it_was_shown_in(self, conversation, reader):
        a, b, c = _record("A"), _record("B"), _record("C")

        turn = record_turn(conversation, "suggest papers", _answer(), listing=_listing(c, a, b))

        snap = snapshot(conversation, reader)
        assert snap.revision == 1 and snap.basis == RECORDED
        assert snap.state.presented == (c.pk, a.pk, b.pk)
        assert snap.answer_turn_id == turn.pk
        assert Turn.objects.get(pk=turn.pk).context_revision == 1

    @pytest.mark.parametrize("state", [PARTIAL, UNAVAILABLE])
    def test_an_undelivered_turn_advances_nothing(self, conversation, reader, state):
        a, b = _record("A"), _record("B")
        record_turn(conversation, "suggest papers", _answer(), listing=_listing(a))

        turn = record_turn(conversation, "more", _answer(state=state), listing=_listing(b))

        snap = snapshot(conversation, reader)
        assert snap.revision == 1
        assert snap.state.presented == (a.pk,)
        assert Turn.objects.get(pk=turn.pk).context_revision is None

    def test_meshkv_follow_ups_keep_the_topic_and_the_pair(self, conversation, reader):
        """A01: suggest two -> compare -> simplify."""
        a, b, c = _record("MeshKV one"), _record("MeshKV two"), _record("Other")
        record_turn(
            conversation, "suggest two MeshKV papers", _answer(),
            listing=_listing(a, b),
            context=ContextState().with_topic("MeshKV").presenting((a.pk, b.pk)),
        )
        record_turn(
            conversation, "compare those two", _answer(a, b),
            context=snapshot(conversation, reader).state.selecting_ordinals(1, 2),
        )

        record_turn(conversation, "simplify that", _answer(a), resolved_question="simplify the MeshKV comparison")

        state = snapshot(conversation, reader).state
        assert state.topic == "MeshKV"
        assert state.presented == (a.pk, b.pk)
        assert state.selected == (a.pk, b.pk)
        assert state.request == "simplify that"
        assert state.retrieval_query == "simplify the MeshKV comparison"
        assert c.pk not in state.presented

    def test_an_answer_citing_papers_never_shown_clears_the_order(self, conversation, reader):
        a, b, other = _record("A"), _record("B"), _record("Other")
        record_turn(conversation, "list", _answer(), listing=_listing(a, b))

        record_turn(conversation, "anything else?", _answer(other))

        assert snapshot(conversation, reader).state.presented == ()

    def test_retrieved_but_unshown_candidates_cannot_be_ordinals(self, conversation, reader):
        """A02: the listing's screened-out candidates were never shown."""
        a, hidden_candidate, b = _record("A"), _record("Unshown"), _record("B")
        listing = _listing(a, b)
        listing["candidates"] = [
            {"record_id": a.pk, "state": "included"},
            {"record_id": hidden_candidate.pk, "state": "excluded"},
            {"record_id": b.pk, "state": "included"},
        ]
        record_turn(conversation, "list", _answer(), listing=listing)

        snap = snapshot(conversation, reader)
        assert snap.ordinal(2) == b.pk
        assert snap.ordinal(3) is None

    def test_find_another_after_a_listing(self, conversation, reader):
        """A03: the exclusions survive the next listing."""
        a, b, c = _record("A"), _record("B"), _record("C")
        record_turn(conversation, "two papers", _answer(), listing=_listing(a, b))

        record_turn(
            conversation, "find another", _answer(), listing=_listing(c),
            context=snapshot(conversation, reader).state.find_another().presenting((c.pk,)),
        )

        state = snapshot(conversation, reader).state
        assert state.excluded == (a.pk, b.pk)
        assert state.presented == (c.pk,)

    def test_deleting_the_conversation_deletes_its_state(self, conversation):
        record_turn(conversation, "list", _answer(), listing=_listing(_record("A")))

        conversation.delete()

        assert not ConversationState.objects.exists()


@pytest.mark.django_db
class RevocationTests:
    def test_a_revoked_paper_keeps_its_position_but_resolves_to_nothing(self, conversation, reader):
        a, b, c = _record("A"), _record("B"), _record("C")
        record_turn(conversation, "list", _answer(), listing=_listing(a, b, c))

        _revoke(b)

        snap = snapshot(conversation, reader)
        assert snap.ordinal(1) == a.pk
        assert snap.ordinal(2) is None
        assert snap.ordinal(3) == c.pk
        assert b.pk not in snap.state.selected + snap.state.excluded

    def test_another_readers_snapshot_reveals_nothing_they_cannot_read(self, conversation):
        a = _record("A")
        record_turn(conversation, "list", _answer(), listing=_listing(a))
        _revoke(a)

        assert snapshot(conversation, make_user("other@cit.edu")).ordinal(1) is None

    def test_a_changed_source_version_is_reported_stale(self, conversation, reader):
        a = _record("A", content_hash="v1")
        record_turn(conversation, "list", _answer(), listing=_listing(a))
        assert snapshot(conversation, reader).stale_sources == frozenset()

        ChunkSet.objects.filter(record=a).update(content_hash="v2")

        assert snapshot(conversation, reader).stale_sources == {a.pk}

    def test_history_and_recall_drop_a_turn_whose_source_was_revoked(self, conversation, reader, embedder, space):
        a, b = _record("A"), _record("B")
        kept = record_turn(conversation, "about b", _answer(b))
        lost = record_turn(conversation, "about a", _answer(a))
        TurnEmbedding.objects.create(
            turn=lost, space=space, kind=TURN_QUESTION_VECTOR,
            embedding=embedder.embed_query("about a"),
        )
        _revoke(a)

        window = recent_window(conversation.turns.all(), user=reader)
        recalled = ConversationMemory().recall(
            conversation, embedder.embed_query("about a"), space.pk
        )

        assert [t.pk for t in window] == [kept.pk]
        assert lost.pk not in [t.pk for t in recalled]
        assert [t.pk for t in readable_turns([kept, lost], reader)] == [kept.pk]


@pytest.mark.django_db
class ReconstructionTests:
    def _legacy(self, conversation, question, answer, listing=None):
        turn = record_turn(conversation, question, answer, listing=listing)
        ConversationState.objects.filter(conversation=conversation).delete()
        Turn.objects.filter(pk=turn.pk).update(context_revision=None)
        return turn

    def test_history_before_state_existed_is_rebuilt_without_being_written(self, conversation, reader):
        a, b = _record("A"), _record("B")
        self._legacy(conversation, "list", _answer(), listing=_listing(a, b))

        snap = snapshot(conversation, reader)

        assert snap.basis == RECONSTRUCTED and snap.revision == 0
        assert snap.state.presented == (a.pk, b.pk)
        assert not ConversationState.objects.exists()

    def test_ambiguous_old_history_stays_unresolved(self, conversation, reader):
        a, b = _record("A"), _record("B")
        self._legacy(conversation, "tell me about these", _answer(a, b))

        snap = snapshot(conversation, reader)

        assert snap.ordinal(1) is None
        assert snap.state.topic == ""

    def test_the_first_new_turn_builds_on_the_reconstruction(self, conversation, reader):
        a, b = _record("A"), _record("B")
        self._legacy(conversation, "list", _answer(), listing=_listing(a, b))

        record_turn(conversation, "explain the first", _answer(a))

        snap = snapshot(conversation, reader)
        assert snap.basis == RECORDED and snap.revision == 1
        assert snap.state.presented == (a.pk, b.pk)


@pytest.mark.django_db
class RevisionTests:
    def test_a_stale_revision_does_not_overwrite_newer_state(self, conversation, reader):
        a, b, c = _record("A"), _record("B"), _record("C")
        record_turn(conversation, "list", _answer(), listing=_listing(a, b))
        seen = snapshot(conversation, reader)
        record_turn(
            conversation, "compare them", _answer(a, b),
            context=seen.state.selecting_ordinals(1, 2), expected_revision=seen.revision,
        )

        stale = record_turn(
            conversation, "another", _answer(), listing=_listing(c),
            context=seen.state.find_another().presenting((c.pk,)),
            expected_revision=seen.revision,
        )

        snap = snapshot(conversation, reader)
        assert snap.basis == CONFLICT and snap.revision == 3
        assert snap.state.selected == (a.pk, b.pk)
        assert snap.state.excluded == ()
        assert snap.ordinal(1) is None
        assert Turn.objects.get(pk=stale.pk).context_revision == 3

    def test_a_fenced_attempt_leaves_the_state_untouched(self, conversation, reader):
        a, b = _record("A"), _record("B")
        record_turn(conversation, "list", _answer(), listing=_listing(a))

        class Fenced(Exception):
            pass

        class _Guard:
            def __enter__(self):
                def written(turn):
                    raise Fenced()
                return written

            def __exit__(self, *exc):
                return False

        with pytest.raises(Fenced):
            record_turn(conversation, "list again", _answer(), listing=_listing(b), guard=_Guard())

        snap = snapshot(conversation, reader)
        assert snap.revision == 1 and snap.state.presented == (a.pk,)
        assert conversation.turns.count() == 1


@pytest.mark.django_db
class HandleTests:
    def test_handles_are_reissued_per_run_and_never_for_revoked_papers(self, conversation, reader):
        from apps.ai.composition import CompositionRoot
        from apps.ai.research.context import Budget, RunContext
        from apps.ai.research.registry import ToolRun

        a, b = _record("A"), _record("B")
        record_turn(conversation, "list", _answer(), listing=_listing(a, b))
        _revoke(b)
        root = CompositionRoot(permits=lambda record: True)

        def run():
            ctx = RunContext(
                user=reader, conversation_id=conversation.pk, scope_record_id=None,
                permits=lambda record: True, lane="research", budget=Budget.from_settings(),
            )
            return ToolRun.start(ctx, root, scoped_handles=True)

        snap = snapshot(conversation, reader)
        first, second = reissue_handles(run(), snap), reissue_handles(run(), snap)

        assert first["presented"][1] is None
        assert first["presented"][0] and first["presented"][0] != second["presented"][0]


@pytest.mark.django_db
class ContextAssemblyTests:
    def test_context_names_the_request_and_bounds_older_turns(self, conversation, reader, settings):
        settings.AI_HISTORY_TOKEN_BUDGET = 40
        a = _record("A")
        old = record_turn(conversation, "first question about A", _answer(a, text="word " * 30))
        for n in range(3):
            record_turn(conversation, f"question {n}", _answer(a, text="word " * 10))

        context = conversation_context(conversation, reader, "simplify", "simplify A")

        assert context.request == "simplify"
        assert context.retrieval_query == "simplify A"
        assert old.pk not in [t.pk for t in context.recent]
        earlier = {entry.turn_id: entry for entry in context.earlier}
        assert earlier[old.pk].depends_on == (a.pk,)

    def test_a_revoked_dependency_removes_the_older_summary(self, conversation, reader, settings):
        settings.AI_HISTORY_TOKEN_BUDGET = 20
        a, b = _record("A"), _record("B")
        old = record_turn(conversation, "first question about A", _answer(a))
        record_turn(conversation, "later about B", _answer(b, text="word " * 10))
        _revoke(a)

        context = conversation_context(conversation, reader, "next", "")

        assert old.pk not in [entry.turn_id for entry in context.earlier]


@pytest.mark.django_db(transaction=True)
class ConcurrencyTests:
    def test_two_simultaneous_completions_cannot_both_apply_stale_state(self):
        """A12: both runs started at revision 1; one wins, one is a conflict."""
        reader = make_user("racer@cit.edu")
        conversation = Conversation.objects.create(user=reader)
        a, b, c, d = _record("A"), _record("B"), _record("C"), _record("D")
        record_turn(conversation, "list", _answer(), listing=_listing(a, b))
        seen = snapshot(conversation, reader)
        barrier = threading.Barrier(2)
        errors = []

        def complete(record):
            try:
                barrier.wait(timeout=10)
                record_turn(
                    conversation, f"another {record.title}", _answer(), listing=_listing(record),
                    context=seen.state.find_another().presenting((record.pk,)),
                    expected_revision=seen.revision,
                )
            except Exception as exc:  # pragma: no cover - surfaced below
                errors.append(exc)
            finally:
                connection.close()

        threads = [threading.Thread(target=complete, args=(r,)) for r in (c, d)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        assert errors == []
        snap = snapshot(conversation, reader)
        assert snap.revision == 3
        assert snap.basis == CONFLICT
        assert snap.state.presented == ()
        assert sorted(Turn.objects.filter(conversation=conversation)
                      .values_list("context_revision", flat=True)) == [1, 2, 3]


class _RecordingLLM:
    """A ScriptedLLM that keeps every prompt it was shown."""

    def __new__(cls):
        from apps.ai.providers.fakes import ScriptedLLM

        class Recording(ScriptedLLM):
            def __init__(self):
                super().__init__()
                self.prompts = []

            def generate(self, system, user):
                self.prompts.append(user)
                return super().generate(system, user)

            def stream(self, system, user):
                self.prompts.append(user)
                return super().stream(system, user)

        return Recording()


@pytest.mark.django_db
class HttpTests:
    def _start(self, client):
        from django.urls import reverse

        return client.post(reverse("ai-conversations"), {}, format="json").json()["id"]

    def test_each_answered_question_advances_one_revision(self, embedder, space, client_for):
        from apps.ai.composition import use_composition_root

        from .corpus import FLOOD_QUESTION, FLOOD_TEXT, ask, make_record, root_with

        reader = make_user("http@cit.edu")
        make_record(title="Flood Prediction", text=FLOOD_TEXT, embedder=embedder, space=space)
        client = client_for(reader)
        conversation_id = self._start(client)

        with use_composition_root(root_with(embedder=embedder)):
            ask(client, FLOOD_QUESTION, conversation_id=conversation_id)
            ask(client, "and its limitations?", conversation_id=conversation_id)

        assert list(Turn.objects.filter(conversation_id=conversation_id)
                    .values_list("context_revision", flat=True)) == [1, 2]
        state = ConversationState.objects.get(conversation_id=conversation_id)
        assert state.revision == 2 and state.request == "and its limitations?"

    def test_a_revoked_turn_never_reaches_the_answering_prompt(self, embedder, space, client_for):
        from apps.ai.composition import use_composition_root

        from .corpus import FLOOD_QUESTION, FLOOD_TEXT, POND_TEXT, ask, make_record, root_with

        reader = make_user("revoked@cit.edu")
        flood = make_record(title="Flood Prediction", text=FLOOD_TEXT, embedder=embedder, space=space)
        make_record(title="Pond Culture", text=POND_TEXT, embedder=embedder, space=space)
        client = client_for(reader)
        conversation_id = self._start(client)
        with use_composition_root(root_with(embedder=embedder)):
            ask(client, FLOOD_QUESTION, conversation_id=conversation_id)
        first = Turn.objects.get(conversation_id=conversation_id)
        assert first.citations.filter(record=flood).exists()
        _revoke(flood)

        llm = _RecordingLLM()
        with use_composition_root(root_with(embedder=embedder, llm=llm)):
            ask(client, "tilapia pond stocking", conversation_id=conversation_id)

        assert llm.prompts
        assert all(FLOOD_QUESTION not in prompt for prompt in llm.prompts)
