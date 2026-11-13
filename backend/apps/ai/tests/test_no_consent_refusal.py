"""IR-792 (ADR-054 decisions 6-8): AI says the owner did not consent.

Real rows through the real disclosure gate; the model is a recording fake.
"""

import pytest
from django.urls import reverse
from django.utils import timezone

from apps.ai.answers.selection import SourceSelection
from apps.ai.composition import CompositionRoot, use_composition_root
from apps.ai.comparison import reader_view
from apps.ai.extraction.gate import NotDisclosed, reading, require_disclosure
from apps.ai.models import ChunkSet, PaperBrief, RecordOverview
from apps.ai.providers.fakes import ScriptedLLM, ScriptedReranker
from apps.records.models import Record
from core.enums import PipelineStatus

from .corpus import FLOOD_TEXT, make_record, make_user

pytestmark = [pytest.mark.db_required, pytest.mark.django_db]


@pytest.fixture(autouse=True)
def queued(monkeypatch):
    """Generation is queued, never inline, so "no vendor" means nothing queued."""
    sent = []
    monkeypatch.setattr(
        "apps.ai.overview.service._enqueue_overview", lambda *args: sent.append(args),
    )
    monkeypatch.setattr("apps.ai.tasks.generate_paper_brief.delay", lambda *args: sent.append(args))
    return sent


def released(record, *, consent, embargoed=False):
    """Set the gate's facts on a real row: released unless ``embargoed``."""
    Record.objects.filter(pk=record.pk).update(
        ai_consent=consent,
        is_embargoed=embargoed,
        embargo_released_at=None if embargoed else timezone.now(),
    )
    record.refresh_from_db()
    return record


def root(embedder, llm):
    # The real gate: no ``permits`` injected.
    return CompositionRoot(embedder=embedder, reranker=ScriptedReranker(), llm=llm)


def overview(client, record):
    return client.get(reverse("ai-record-overview", args=[record.pk]))


class TestAiOverview:
    def test_a_yes_paper_queues_generation(
        self, embedder, space, client_for, queued, django_capture_on_commit_callbacks,
    ):
        # The control: without it, "nothing queued" below could pass by construction.
        reader = make_user("yes-reader@cit.edu")
        record = released(
            make_record(title="Yes Paper", text=FLOOD_TEXT, embedder=embedder, space=space),
            consent=True,
        )

        with use_composition_root(root(embedder, ScriptedLLM(reply="unused"))):
            with django_capture_on_commit_callbacks(execute=True):
                response = overview(client_for(reader), record)

        assert response.json()["state"] == "generating"
        assert len(queued) == 1

    def test_a_no_paper_says_the_owner_did_not_consent_and_sends_nothing(
        self, embedder, space, client_for, queued, django_capture_on_commit_callbacks,
    ):
        reader = make_user("no-reader@cit.edu")
        record = released(
            make_record(title="No Paper", text=FLOOD_TEXT, embedder=embedder, space=space),
            consent=False,
        )
        llm = ScriptedLLM(reply="Should never be asked [p. 4].")

        with use_composition_root(root(embedder, llm)):
            with django_capture_on_commit_callbacks(execute=True):
                response = overview(client_for(reader), record)

        assert response.status_code == 200
        assert response.json() == {"state": "unavailable", "overview": None, "reason": "no_consent"}
        assert queued == []
        assert llm.calls == []
        assert not RecordOverview.objects.filter(record=record).exists()

    def test_the_owner_is_told_too(
        self, embedder, space, client_for, queued, django_capture_on_commit_callbacks,
    ):
        owner = make_user("no-owner@cit.edu")
        record = released(
            make_record(
                title="Own No Draft", text=FLOOD_TEXT, embedder=embedder, space=space,
                status=PipelineStatus.DRAFT, owner=owner,
            ),
            consent=False,
        )
        with use_composition_root(root(embedder, ScriptedLLM(reply="unused"))):
            with django_capture_on_commit_callbacks(execute=True):
                response = overview(client_for(owner), record)

        assert response.json()["reason"] == "no_consent"
        assert queued == []
        assert not RecordOverview.objects.filter(record=record).exists()

    def test_a_no_and_embargoed_paper_names_consent_and_never_the_embargo(
        self, embedder, space, client_for,
    ):
        reader = make_user("both-reader@cit.edu")
        record = released(
            make_record(title="Both Paper", text=FLOOD_TEXT, embedder=embedder, space=space),
            consent=False, embargoed=True,
        )

        with use_composition_root(root(embedder, ScriptedLLM(reply="unused"))):
            response = overview(client_for(reader), record)

        assert response.json() == {"state": "unavailable", "overview": None, "reason": "no_consent"}
        assert "embargo" not in response.content.decode().lower()

    def test_an_embargo_alone_gives_no_reason(self, embedder, space, client_for):
        reader = make_user("embargo-reader@cit.edu")
        record = released(
            make_record(title="Embargo Paper", text=FLOOD_TEXT, embedder=embedder, space=space),
            consent=True, embargoed=True,
        )

        with use_composition_root(root(embedder, ScriptedLLM(reply="unused"))):
            response = overview(client_for(reader), record)

        assert response.json() == {"state": "unavailable", "overview": None}

    def test_no_stored_answer_is_not_reported_as_a_no(self, embedder, space, client_for):
        reader = make_user("unanswered-reader@cit.edu")
        record = released(
            make_record(title="Unanswered Paper", text=FLOOD_TEXT, embedder=embedder, space=space),
            consent=None,
        )

        with use_composition_root(root(embedder, ScriptedLLM(reply="unused"))):
            response = overview(client_for(reader), record)

        assert response.json() == {"state": "unavailable", "overview": None}


class TestPaperBrief:
    @pytest.fixture(autouse=True)
    def briefs_on(self, settings):
        settings.AI_PAPER_BRIEFS_ENABLED = True

    def brief(self, client, record):
        return client.post(reverse("ai-paper-brief", args=[record.pk]), {}, format="json")

    def test_a_no_paper_brief_says_the_owner_did_not_consent(
        self, embedder, space, client_for, queued, django_capture_on_commit_callbacks,
    ):
        reader = make_user("brief-no@cit.edu")
        record = released(
            make_record(title="Brief No", text=FLOOD_TEXT, embedder=embedder, space=space),
            consent=False,
        )
        with use_composition_root(root(embedder, ScriptedLLM(reply="unused"))):
            with django_capture_on_commit_callbacks(execute=True):
                response = self.brief(client_for(reader), record)

        assert response.json() == {"state": "unavailable", "brief": None, "reason": "no_consent"}
        assert queued == []
        assert not PaperBrief.objects.filter(record=record).exists()

    def test_an_embargoed_brief_keeps_the_generic_reason(self, embedder, space, client_for):
        reader = make_user("brief-embargo@cit.edu")
        record = released(
            make_record(title="Brief Embargo", text=FLOOD_TEXT, embedder=embedder, space=space),
            consent=True, embargoed=True,
        )

        with use_composition_root(root(embedder, ScriptedLLM(reply="unused"))):
            response = self.brief(client_for(reader), record)

        assert response.json()["reason"] == "disclosure_or_access"


class TestGeneralAskIris:
    def test_a_no_paper_never_reaches_the_model(self, embedder, space):
        asker = make_user("ask-general@cit.edu")
        yes = released(
            make_record(title="Yes Flood Paper", text=FLOOD_TEXT, embedder=embedder, space=space),
            consent=True,
        )
        no = released(
            make_record(title="No Flood Paper", text=FLOOD_TEXT, embedder=embedder, space=space),
            consent=False,
        )

        with use_composition_root(root(embedder, ScriptedLLM(reply="unused"))) as active:
            result = active.retriever().retrieve("rainfall gauges flood", asker)
        shown = SourceSelection().apply(result.passages)

        assert no.pk in {passage.record_id for passage in result.passages}
        assert yes.pk in {passage.record_id for passage in shown}
        assert no.pk not in {passage.record_id for passage in shown}

    def test_a_person_who_said_no_still_finds_yes_papers(self, embedder, space):
        asker = make_user("ask-said-no@cit.edu")
        asker.ai_consent = False
        asker.save(update_fields=["ai_consent"])
        yes = released(
            make_record(title="Yes For No Asker", text=FLOOD_TEXT, embedder=embedder, space=space),
            consent=True,
        )

        with use_composition_root(root(embedder, ScriptedLLM(reply="unused"))) as active:
            result = active.retriever().retrieve("rainfall gauges flood", asker)

        assert yes.pk in {p.record_id for p in SourceSelection().apply(result.passages)}


class TestStoredComparison:
    def comparison(self, *records):
        versions = []
        for record in records:
            chunk_set = ChunkSet.objects.get(record=record, is_active=True)
            versions.append({
                "record_id": record.pk, "chunk_set_id": chunk_set.pk,
                "content_hash": chunk_set.content_hash,
            })
        return {
            "source_versions": versions,
            "records": [{"record_id": record.pk} for record in records],
            "rows": [],
        }

    def test_a_comparison_including_a_no_paper_is_withheld(self, embedder, space):
        reader = make_user("compare-reader@cit.edu")
        yes = released(
            make_record(title="Compare Yes", text=FLOOD_TEXT, embedder=embedder, space=space),
            consent=True,
        )
        no = released(
            make_record(title="Compare No", text=FLOOD_TEXT, embedder=embedder, space=space),
            consent=False,
        )

        with use_composition_root(root(embedder, ScriptedLLM(reply="unused"))):
            assert reader_view(self.comparison(yes), reader) is not None
            assert reader_view(self.comparison(yes, no), reader) is None


class TestThirdPartyReader:
    def test_a_no_paper_is_not_sent_to_an_outside_reader(self, embedder, space):
        no = released(
            make_record(title="Read No", text=FLOOD_TEXT, embedder=embedder, space=space),
            consent=False,
        )
        yes = released(
            make_record(title="Read Yes", text=FLOOD_TEXT, embedder=embedder, space=space),
            consent=True,
        )

        with reading(yes.pk):
            require_disclosure()
        with reading(no.pk), pytest.raises(NotDisclosed):
            require_disclosure()
