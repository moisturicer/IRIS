"""An extraction that leaves campus is gated and admitted (IR-850, ADR-056 §5-6).

The in-memory Extractor stands in for LlamaParse with ``leaves_campus=True``.
Admission writes through its own connection, so these run against real
Postgres with committed transactions.
"""

from datetime import date
from decimal import Decimal

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone

from apps.ai.admission.tests.support import enforce
from apps.ai.chunking.document import PARAGRAPH, DocumentElement, NormalizedDocument
from apps.ai.extraction import InMemoryExtractor, Usage, use_extractor
from apps.ai.extraction.tests.fixtures import FIXTURES, pdf_bytes
from apps.ai.models import ProviderCampaign, ProviderReservation
from apps.ai.models.admission import RELEASED, SETTLED
from apps.documents import tasks
from apps.documents.models import DocumentKind, PdfExtraction
from apps.documents.phases import ExtractionPhase
from apps.documents.sources import reset_manuscript
from apps.records.models import Record, RecordType

pytestmark = [
    pytest.mark.db_required,
    pytest.mark.django_db(transaction=True, databases=["default", "admission"]),
]

DOCUMENT = NormalizedDocument(
    title="Tilapia feed",
    elements=(DocumentElement(kind=PARAGRAPH, text="Samples were collected weekly.", page=1),),
    page_sizes={1: (612.0, 792.0)},
)

FIXTURE = next(f for f in FIXTURES.values() if len(f.pages) > 1)
PDF = pdf_bytes(FIXTURE)
PAGES = len(FIXTURE.pages)

#: Placeholders for tests only: nothing here is an approved price.
PRICES = {
    "AI_ADMISSION_LANE_CONCURRENCY": '{"extraction": 2}',
    "AI_ADMISSION_EXTRACTION_CREDIT_USD": "0.00125",
    "AI_ADMISSION_EXTRACTION_CREDITS_PER_PAGE": "10",
    "AI_ADMISSION_EXTRACTION_ADDON_CREDITS_PER_PAGE": "2",
}


@pytest.fixture(autouse=True)
def queued(monkeypatch):
    """Celery calls the code under test would make, recorded, not run."""
    calls = []
    monkeypatch.setattr(tasks, "_queue_chunk_extraction", lambda *args: calls.append(("chunk", args)))
    monkeypatch.setattr(tasks.extract_manuscript_text, "delay", lambda *args: calls.append(("read", args)))
    monkeypatch.setattr(tasks.extract_pdf_text, "delay", lambda *args: calls.append(("read_upload", args)))
    return calls


@pytest.fixture
def enforced(settings):
    enforce(settings, **PRICES)


def _record(*, consent=True, embargo=None, answered=True):
    record = Record.objects.create(
        title="A thesis",
        record_type=RecordType.objects.get_or_create(name="Thesis")[0],
        abstract_file=SimpleUploadedFile("thesis.pdf", PDF),
        embargo_answered_at=timezone.now() if answered else None,
        embargoed_until=embargo,
        dpa_accepted_at=timezone.now() if consent else None,
    )
    PdfExtraction.objects.create(
        record=record, kind=DocumentKind.MANUSCRIPT, source_revision=record.manuscript_revision,
    )
    return record


def _offcampus(**kwargs):
    kwargs.setdefault("usage", Usage(pages=3, credits=Decimal("24")))
    return InMemoryExtractor(DOCUMENT, leaves_campus=True, **kwargs)


def _revision(record):
    return str(record.manuscript_revision) if record.manuscript_revision else None


def _read_of(record):
    return ("read", (record.pk, _revision(record)))


def _run(extractor, record):
    with use_extractor(extractor):
        return tasks.extract_manuscript_text.apply(args=[record.pk, _revision(record)])


def _reservations():
    return ProviderReservation.objects.using("admission").all()


def _charged_micros():
    campaign = ProviderCampaign.objects.using("admission").first()
    return 0 if campaign is None else campaign.charged_cost_micros


def _extraction(record):
    return PdfExtraction.objects.get(record=record)


def test_a_paper_without_consent_is_not_sent(enforced):
    record = _record(consent=False)
    extractor = _offcampus()

    _run(extractor, record)

    assert extractor.calls == []
    extraction = _extraction(record)
    assert extraction.phase == ExtractionPhase.AWAITING_DISCLOSURE
    assert extraction.status == "queued"
    # Refused inside the attempt: its reservation is released, not charged.
    assert [r.state for r in _reservations()] == [RELEASED]
    assert _charged_micros() == 0


def test_a_paper_under_embargo_is_not_sent(enforced):
    record = _record(embargo=date(2030, 1, 1))
    extractor = _offcampus()

    _run(extractor, record)

    assert extractor.calls == []
    assert _extraction(record).phase == ExtractionPhase.AWAITING_DISCLOSURE
    assert _charged_micros() == 0


def test_a_paper_nobody_answered_the_embargo_for_is_not_sent(enforced):
    record = _record(answered=False)
    extractor = _offcampus()

    _run(extractor, record)

    assert extractor.calls == []
    assert _extraction(record).phase == ExtractionPhase.AWAITING_DISCLOSURE


def test_an_eligible_paper_is_reserved_at_its_pages_and_settled_to_the_credits_reported(enforced):
    record = _record()
    extractor = _offcampus(usage=Usage(pages=PAGES, credits=Decimal("24")))

    _run(extractor, record)

    assert len(extractor.calls) == 1
    extraction = _extraction(record)
    assert (extraction.status, extraction.phase) == ("done", ExtractionPhase.READY)
    (reservation,) = _reservations()
    assert reservation.lane == "extraction"
    assert reservation.operation == "extraction"
    # PAGES x (10 tier + 2 add-on credits) x US$0.00125 a credit.
    assert reservation.reserved_cost_micros == PAGES * 15_000
    assert reservation.state == SETTLED
    assert reservation.charge_cost_micros == 30_000  # 24 credits
    assert _charged_micros() == 30_000


@pytest.mark.parametrize("usage", [Usage(pages=PAGES, credits=None), None], ids=["no-credits", "no-usage"])
def test_unreported_usage_stays_charged_at_its_reservation(enforced, usage):
    record = _record()

    _run(_offcampus(usage=usage), record)

    (reservation,) = _reservations()
    assert reservation.state == SETTLED
    assert reservation.charge_cost_micros == reservation.reserved_cost_micros == PAGES * 15_000
    assert _charged_micros() == PAGES * 15_000


def test_with_admission_off_nothing_is_sent(settings):
    settings.AI_PROVIDER_ADMISSION = "off"
    record = _record()
    extractor = _offcampus()

    result = _run(extractor, record)

    assert extractor.calls == []
    assert result.failed()
    assert _extraction(record).status == "failed"
    assert not _reservations().exists()


@pytest.mark.parametrize("unset", [
    "AI_ADMISSION_EXTRACTION_CREDIT_USD",
    "AI_ADMISSION_EXTRACTION_CREDITS_PER_PAGE",
    "AI_ADMISSION_EXTRACTION_ADDON_CREDITS_PER_PAGE",
])
def test_an_unset_extraction_price_refuses_the_read(settings, unset):
    enforce(settings, **{**PRICES, unset: ""})
    record = _record()
    extractor = _offcampus()

    _run(extractor, record)

    assert extractor.calls == []
    assert _extraction(record).status == "failed"
    assert not _reservations().exists()


def test_an_extraction_lane_not_configured_refuses_the_read(settings):
    enforce(settings, **{**PRICES, "AI_ADMISSION_LANE_CONCURRENCY": '{"chat": 1}'})
    record = _record()
    extractor = _offcampus()

    _run(extractor, record)

    assert extractor.calls == []


def test_a_local_extractor_is_neither_gated_nor_admitted(settings):
    settings.AI_PROVIDER_ADMISSION = "off"
    record = _record(consent=False, embargo=date(2030, 1, 1))
    extractor = InMemoryExtractor(DOCUMENT)

    _run(extractor, record)

    assert len(extractor.calls) == 1
    assert _extraction(record).status == "done"


def test_a_token_price_for_the_same_name_cannot_settle_an_unreported_read_lower(settings):
    enforce(settings, **PRICES, AI_ADMISSION_PRICES='{"memory": {"input": 1.0, "output": 1.0}}')
    record = _record()

    _run(_offcampus(usage=None), record)

    (reservation,) = _reservations()
    assert reservation.charge_cost_micros == PAGES * 15_000


# -- queued only when the gate allows -------------------------------------------


def _queue(record):
    from django.db import transaction

    with transaction.atomic():
        reset_manuscript(Record.objects.select_for_update().get(pk=record.pk), retry=True)


def test_a_read_the_gate_refuses_is_not_queued(enforced, queued):
    record = _record(consent=False)

    with use_extractor(_offcampus()):
        _queue(record)

    assert [call for call in queued if call[0] == "read"] == []
    extraction = _extraction(record)
    assert extraction.phase == ExtractionPhase.AWAITING_DISCLOSURE
    assert extraction.status == "queued"


def test_a_read_the_gate_allows_is_queued(enforced, queued):
    record = _record()

    with use_extractor(_offcampus()):
        _queue(record)

    assert _read_of(record) in queued
    assert _extraction(record).phase == ExtractionPhase.QUEUED


def test_a_local_extractor_is_queued_whatever_the_gate_says(queued):
    record = _record(consent=False, embargo=date(2030, 1, 1))

    with use_extractor(InMemoryExtractor(DOCUMENT)):
        _queue(record)

    assert _read_of(record) in queued


def test_a_consent_withdrawn_while_queued_is_honoured_at_send(enforced, queued):
    record = _record()
    extractor = _offcampus()
    with use_extractor(extractor):
        _queue(record)
    Record.objects.filter(pk=record.pk).update(dpa_accepted_at=None)

    _run(extractor, record)

    assert extractor.calls == []
    assert _extraction(record).phase == ExtractionPhase.AWAITING_DISCLOSURE
    assert _charged_micros() == 0


# -- a later Yes or release queues the read -------------------------------------


@pytest.fixture
def ai_sends(monkeypatch):
    """Indexing and the overview are another ticket's; only the read matters here."""
    from apps.ai import tasks as ai_tasks
    from apps.ai.overview import service

    monkeypatch.setattr(ai_tasks.index_record, "delay", lambda *args, **kwargs: None)
    monkeypatch.setattr(service, "overview_for", lambda *args, **kwargs: None)


def test_a_release_queues_the_read_and_it_is_then_sent(enforced, queued, ai_sends):
    from django.db import transaction

    from apps.accounts.models import User
    from apps.records.embargo import release_embargo

    record = _record(embargo=date(2030, 1, 1))
    extractor = _offcampus()
    with use_extractor(extractor):
        _queue(record)
        assert [call for call in queued if call[0] == "read"] == []

        actor = User.objects.create_user(email="rdco@cit.edu", password="x")
        with transaction.atomic():
            release_embargo(Record.objects.select_for_update().get(pk=record.pk), actor=actor)

        assert _read_of(record) in queued
        assert _extraction(record).phase == ExtractionPhase.QUEUED
        _run(extractor, record)

    assert len(extractor.calls) == 1
    assert _extraction(record).status == "done"


def test_a_later_yes_queues_the_read(enforced, queued, ai_sends):
    from django.db import transaction

    from apps.ai.tasks import send_to_ai_on_commit

    record = _record(consent=False)
    with use_extractor(_offcampus()):
        _queue(record)
        with transaction.atomic():
            Record.objects.filter(pk=record.pk).update(dpa_accepted_at=timezone.now())
            send_to_ai_on_commit(record.pk)

    assert _read_of(record) in queued


def test_an_act_that_leaves_the_gate_shut_queues_nothing(enforced, queued, ai_sends):
    from django.db import transaction

    from apps.ai.tasks import send_to_ai_on_commit

    record = _record(consent=False)
    with use_extractor(_offcampus()):
        _queue(record)
        with transaction.atomic():
            send_to_ai_on_commit(record.pk)

    assert [call for call in queued if call[0] == "read"] == []
    assert _extraction(record).phase == ExtractionPhase.AWAITING_DISCLOSURE


# -- supplementary uploads ------------------------------------------------------


def _upload(record):
    from apps.documents.models import RecordUpload, UploadSlot
    from apps.documents.sources import queue_upload_read

    slot = UploadSlot.objects.create(record_type=record.record_type, name="Ethics Clearance")
    upload = RecordUpload.objects.create(
        record=record, slot=slot, file=SimpleUploadedFile("ethics.pdf", PDF),
    )
    from django.db import transaction

    with transaction.atomic():
        queue_upload_read(upload)
    return upload


def test_a_supplementary_upload_waits_for_the_gate_and_a_release_queues_it(enforced, queued, ai_sends):
    from django.db import transaction

    from apps.accounts.models import User
    from apps.records.embargo import release_embargo

    record = _record(embargo=date(2030, 1, 1))
    with use_extractor(_offcampus()):
        upload = _upload(record)
        assert ("read_upload", (upload.pk,)) not in queued
        assert upload.pdf_extraction.phase == ExtractionPhase.AWAITING_DISCLOSURE

        actor = User.objects.create_user(email="rdco@cit.edu", password="x")
        with transaction.atomic():
            release_embargo(Record.objects.select_for_update().get(pk=record.pk), actor=actor)

    assert ("read_upload", (upload.pk,)) in queued
    upload.pdf_extraction.refresh_from_db()
    assert upload.pdf_extraction.phase == ExtractionPhase.QUEUED


def test_a_supplementary_upload_for_a_local_extractor_is_queued_at_once(queued):
    record = _record(consent=False)
    with use_extractor(InMemoryExtractor(DOCUMENT)):
        upload = _upload(record)

    assert ("read_upload", (upload.pk,)) in queued
    assert upload.pdf_extraction.kind == DocumentKind.SUPPLEMENTARY


def test_publish_does_not_wait_on_a_held_read(enforced, queued):
    from apps.records.metadata_suggestions import suggestions_payload

    record = _record(consent=False)
    with use_extractor(_offcampus()):
        _queue(record)

    payload = suggestions_payload(Record.objects.get(pk=record.pk))
    assert payload["state"] == "unsupported"
    assert payload["phase"] == ExtractionPhase.AWAITING_DISCLOSURE
    assert payload["message"].startswith("Not read: awaiting consent or release")


def test_a_read_that_names_no_record_is_not_sent(enforced):
    from apps.ai.extraction import current_extractor
    from apps.ai.extraction.gate import NotDisclosed

    extractor = _offcampus()
    with use_extractor(extractor), pytest.raises(NotDisclosed):
        current_extractor().extract(PDF, filename="thesis.pdf")

    assert extractor.calls == []
    assert _charged_micros() == 0


def test_a_release_that_lands_just_after_the_refusal_still_queues_the_read(enforced, queued, ai_sends, monkeypatch):
    """The release commits between the send-time refusal and the task holding the row."""
    from django.db import transaction

    from apps.accounts.models import User
    from apps.ai.extraction import gate
    from apps.records.embargo import release_embargo

    record = _record(embargo=date(2030, 1, 1))
    actor = User.objects.create_user(email="rdco@cit.edu", password="x")
    refuse = gate.require_disclosure

    def refused_then_released():
        try:
            refuse()
        finally:
            with transaction.atomic():
                release_embargo(Record.objects.select_for_update().get(pk=record.pk), actor=actor)

    monkeypatch.setattr(gate, "require_disclosure", refused_then_released)
    queued.clear()

    _run(_offcampus(), record)

    assert _read_of(record) in queued
    assert _extraction(record).phase == ExtractionPhase.QUEUED
