"""Unstructured's read is admitted at its flat US$ per page (IR-983, ADR-041).

Unstructured reports pages, not credits, so a read settles to pages x price.
"""

from io import StringIO

import pytest
from django.core.management import call_command

from apps.ai.admission import errors
from apps.ai.admission.extraction import AdmittedExtractor
from apps.ai.admission.tests.support import enforce
from apps.ai.extraction import InMemoryExtractor, Usage
from apps.ai.models.admission import SETTLED
from apps.documents.tests.test_offcampus_extraction import (  # noqa: F401  (queued is autouse)
    DOCUMENT,
    PAGES,
    PDF,
    _charged_micros,
    _extraction,
    _record,
    _reservations,
    _run,
    queued,
)

pytestmark = [
    pytest.mark.db_required,
    pytest.mark.django_db(transaction=True, databases=["default", "admission"]),
]

UNSTRUCTURED_PRICE = "AI_ADMISSION_EXTRACTION_UNSTRUCTURED_USD_PER_PAGE"
#: Placeholders for tests only: nothing here is an approved price.
PRICES = {
    "AI_ADMISSION_LANE_CONCURRENCY": '{"extraction": 2}',
    UNSTRUCTURED_PRICE: "0.01",
}


def _unstructured(usage):
    adapter = InMemoryExtractor(DOCUMENT, leaves_campus=True, usage=usage)
    adapter.extractor_name = "unstructured"
    return adapter


def _select(monkeypatch, backend):
    from apps.ai.extraction import selection

    monkeypatch.setattr(selection, "selected_backend", lambda: backend)


def test_an_unstructured_read_reserves_and_settles_in_usd_per_page(settings):
    enforce(settings, **PRICES)
    record = _record()

    _run(_unstructured(Usage(pages=3, credits=None)), record)

    assert _extraction(record).status == "done"
    (reservation,) = _reservations()
    assert reservation.reserved_cost_micros == PAGES * 10_000
    assert reservation.state == SETTLED
    assert reservation.charge_cost_micros == 30_000
    assert _charged_micros() == 30_000


def test_an_unstructured_read_with_no_usage_stays_at_its_reservation(settings):
    enforce(settings, **PRICES)
    record = _record()

    _run(_unstructured(None), record)

    (reservation,) = _reservations()
    assert reservation.charge_cost_micros == reservation.reserved_cost_micros == PAGES * 10_000


def test_a_missing_unstructured_price_refuses_as_not_configured(settings):
    enforce(settings, **{
        **PRICES, UNSTRUCTURED_PRICE: "",
    })
    adapter = _unstructured(Usage(pages=3))

    with pytest.raises(errors.AdmissionDenied) as refused:
        AdmittedExtractor(adapter).extract(PDF, filename="thesis.pdf")

    assert refused.value.reason == errors.NOT_CONFIGURED
    assert adapter.calls == []
    assert not _reservations().exists()


def test_an_unnamed_adapter_is_priced_as_the_selected_backend(settings, monkeypatch):
    enforce(settings, **{**PRICES, UNSTRUCTURED_PRICE: ""})
    _select(monkeypatch, "unstructured")
    adapter = InMemoryExtractor(DOCUMENT, leaves_campus=True, usage=Usage(pages=3))

    with pytest.raises(errors.AdmissionDenied) as refused:
        AdmittedExtractor(adapter).extract(PDF, filename="thesis.pdf")

    assert refused.value.reason == errors.NOT_CONFIGURED


def test_provider_campaign_names_the_selected_backends_missing_price(settings, monkeypatch):
    enforce(settings, **{**PRICES, UNSTRUCTURED_PRICE: ""})
    _select(monkeypatch, "unstructured")
    out = StringIO()

    call_command("provider_campaign", stdout=out)

    assert f"extraction price (unstructured) not configured: {UNSTRUCTURED_PRICE}" in out.getvalue()
