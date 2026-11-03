"""IR-720: the outbound guard rechecks every governing fact at send time."""

import pytest

from apps.ai.models import ChunkSet
from apps.ai.policy.outbound import Dependency, OutboundGuard
from apps.ai.tests.corpus import make_user
from apps.records.models import Record, RecordOwner
from core.enums import PipelineStatus

pytestmark = [pytest.mark.db_required, pytest.mark.django_db]

MODEL = "fake-model"


def paper(title, *, status=PipelineStatus.PUBLISHED, owner=None, version=None):
    record = Record.objects.create(title=title, abstract=f"About {title}.", pipeline_status=status)
    if owner is not None:
        RecordOwner.objects.create(record=record, user=owner, is_primary=True)
    ChunkSet.objects.create(
        record=record, extraction_hash=f"e{title}", strategy_id="s", options={},
        content_hash=version or f"c{title}", is_active=True, page_sizes={},
    )
    return record


def passage(record):
    return Dependency.passage(record.pk, f"c{record.title}")


def guard(reader, *, embargoed=(), scope=None, models=(MODEL,)):
    return OutboundGuard(
        principal=reader, scope_record_id=scope,
        permits=lambda record: record.pk not in embargoed,
        provider_permits=lambda model: model in models,
    )


@pytest.fixture
def reader():
    return make_user("guard@cit.edu")


def test_a_readable_disclosable_current_source_is_permitted(reader):
    flood = paper("Flood")
    result = guard(reader).authorize([passage(flood)], model=MODEL)
    assert result.allowed
    assert result.permitted == {passage(flood)}


def test_a_source_that_may_not_be_disclosed_is_withheld_and_the_rest_stays_usable(reader):
    flood, pond = paper("Flood"), paper("Pond")
    result = guard(reader, embargoed={pond.pk}).authorize(
        [passage(flood), passage(pond)], model=MODEL)
    assert not result.allowed
    assert result.permitted == {passage(flood)}
    assert result.denied == {passage(pond)}


def test_a_source_the_reader_can_no_longer_read_is_withheld(reader):
    flood = paper("Flood")
    Record.objects.filter(pk=flood.pk).update(pipeline_status=PipelineStatus.DRAFT)
    assert guard(reader).authorize([passage(flood)], model=MODEL).denied == {passage(flood)}


def test_reading_permission_alone_never_permits_transmission(reader):
    draft = paper("Own draft", status=PipelineStatus.DRAFT, owner=reader)
    readable = guard(reader).authorize([passage(draft)], model=MODEL)
    embargoed = guard(reader, embargoed={draft.pk}).authorize([passage(draft)], model=MODEL)
    assert readable.allowed and not embargoed.allowed


def test_a_source_outside_the_paper_chat_scope_is_withheld(reader):
    flood, pond = paper("Flood"), paper("Pond")
    result = guard(reader, scope=flood.pk).authorize([passage(flood), passage(pond)], model=MODEL)
    assert result.permitted == {passage(flood)}


def test_a_passage_whose_paper_was_rechunked_since_it_was_read_is_withheld(reader):
    flood = paper("Flood")
    read = passage(flood)
    ChunkSet.objects.filter(record=flood, is_active=True).update(content_hash="replaced")
    assert guard(reader).authorize([read], model=MODEL).denied == {read}


def test_an_abstract_changed_since_it_was_read_is_withheld(reader):
    flood = paper("Flood")
    read = Dependency.abstract(flood.pk, flood.title, flood.abstract)
    assert guard(reader).authorize([read], model=MODEL).allowed
    Record.objects.filter(pk=flood.pk).update(abstract="Rewritten.")
    assert guard(reader).authorize([read], model=MODEL).denied == {read}


@pytest.mark.parametrize("model", ["unlisted-model", None])
def test_a_recipient_without_a_known_provider_policy_receives_nothing(reader, model):
    flood = paper("Flood")
    result = guard(reader).authorize([passage(flood)], model=model)
    assert not result.allowed and result.provider_refused
    assert result.permitted == frozenset()


def test_by_default_unknown_disclosure_facts_refuse_transmission(reader):
    # An unanswered embargo is Unknown (ADR-052), so the real gate refuses.
    flood = paper("Flood")
    result = OutboundGuard(principal=reader, provider_permits=lambda model: True).authorize(
        [passage(flood)], model=MODEL)
    assert result.denied == {passage(flood)}


def test_the_default_provider_policy_knows_only_configured_no_training_models(settings):
    from apps.ai.policy.outbound import configured_provider_permits

    settings.VOYAGE_EMBED_MODEL = "voyage-context-4"
    settings.LLM_ANSWER_MODEL = "answer-model"
    assert configured_provider_permits("voyage-context-4")
    assert configured_provider_permits("answer-model")
    assert not configured_provider_permits("somebody-elses-model")
    assert not configured_provider_permits(None)


def test_a_derived_artifact_survives_only_if_every_source_it_used_is_permitted(reader):
    flood, pond = paper("Flood"), paper("Pond")
    result = guard(reader, embargoed={pond.pk}).authorize(
        [passage(flood), passage(pond)], model=MODEL)
    artifacts = [
        ("flood finding", {passage(flood)}),
        ("comparison of both", {passage(flood), passage(pond)}),
        ("pond finding", {passage(pond)}),
    ]
    kept = result.retain(artifacts, lambda artifact: artifact[1])
    assert [text for text, _ in kept] == ["flood finding"]


def test_the_reader_facing_limitation_names_no_withheld_source(reader):
    pond = paper("Secret pond study")
    withheld = guard(reader, embargoed={pond.pk}).authorize([passage(pond)], model=MODEL)
    permitted = guard(reader).authorize([passage(pond)], model=MODEL)
    assert permitted.limitation is None
    assert withheld.limitation == "source_unavailable"
    many = guard(reader, embargoed={pond.pk}).authorize(
        [passage(pond), Dependency.metadata(pond.pk)], model=MODEL)
    assert many.limitation == withheld.limitation


# -- the real gate on IR-811's stored embargo answer (ADR-052) ----------------

def answered(title, *, until=None, owner=None):
    """A consented, non-IP paper whose embargo was answered through the writer."""
    from django.utils import timezone

    from apps.records.embargo import EmbargoAnswer, record_answer

    record = paper(title, owner=owner)
    Record.objects.filter(pk=record.pk).update(is_ip=False, dpa_accepted_at=timezone.now())
    record.refresh_from_db()
    record_answer(record, EmbargoAnswer(until=until), actor=owner)
    return record


def real_gate(reader):
    return OutboundGuard(principal=reader, provider_permits=lambda model: True)


def test_an_embargo_answered_after_a_read_withholds_only_that_paper(reader):
    from datetime import timedelta

    from django.utils import timezone

    from apps.records.embargo import EmbargoAnswer, record_answer

    flood, pond = answered("Flood"), answered("Pond")
    read = [passage(flood), passage(pond)]
    assert real_gate(reader).authorize(read, model=MODEL).allowed
    record_answer(pond, EmbargoAnswer(until=timezone.localdate() + timedelta(days=30)), actor=None)
    result = real_gate(reader).authorize(read, model=MODEL)
    assert result.permitted == {passage(flood)}
    assert result.denied == {passage(pond)}


def test_an_unanswered_paper_the_reader_owns_is_readable_but_never_sent(reader):
    draft = paper("Own draft", status=PipelineStatus.DRAFT, owner=reader)
    result = real_gate(reader).authorize([passage(draft)], model=MODEL)
    assert result.denied == {passage(draft)}


@pytest.mark.parametrize("change", [{"dpa_accepted_at": None}, {"is_ip": True}])
def test_withdrawn_consent_or_an_ip_mark_withholds_a_paper_read_earlier(reader, change):
    flood = answered("Flood")
    read = passage(flood)
    assert real_gate(reader).authorize([read], model=MODEL).allowed
    Record.objects.filter(pk=flood.pk).update(**change)
    assert real_gate(reader).authorize([read], model=MODEL).denied == {read}
