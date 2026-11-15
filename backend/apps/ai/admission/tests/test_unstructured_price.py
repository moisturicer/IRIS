"""Unstructured's extraction price: flat US$ per page, never defaulted (IR-983)."""

from decimal import Decimal

import pytest
from django.core.exceptions import ImproperlyConfigured

from apps.ai.admission.limits import (
    NotConfigured,
    extraction_settings,
    read_extraction_price,
    verify_admission_configuration,
)

from .support import enforce

pytestmark = pytest.mark.django_required

NAME = "AI_ADMISSION_EXTRACTION_UNSTRUCTURED_USD_PER_PAGE"


def _select(monkeypatch, backend):
    from apps.ai.extraction import selection

    monkeypatch.setattr(selection, "selected_backend", lambda: backend)


def test_unstructured_is_one_credit_a_page_at_its_usd_price(settings):
    enforce(settings, **{NAME: "0.01"})
    price = read_extraction_price("unstructured")
    assert (price.credit_usd, price.credits_per_page, price.addon_credits_per_page) == (
        Decimal("0.01"), Decimal(1), Decimal(0),
    )
    assert price.reserve_micros(7) == 70_000


def test_an_unset_unstructured_price_is_not_configured_and_never_defaulted(settings):
    enforce(settings, **{NAME: ""})
    with pytest.raises(NotConfigured, match=NAME):
        read_extraction_price("unstructured")
    verify_admission_configuration()


def test_the_selected_backend_picks_the_price(settings, monkeypatch):
    enforce(settings, **{NAME: ""})
    _select(monkeypatch, "unstructured")
    with pytest.raises(NotConfigured, match=NAME):
        read_extraction_price()
    assert extraction_settings() == (NAME,)
    _select(monkeypatch, "llamaparse")
    assert NAME not in extraction_settings()


@pytest.mark.parametrize("value", ["free", "0", "-0.01", "NaN"])
def test_a_malformed_unstructured_price_stops_startup(settings, value):
    enforce(settings, **{NAME: value})
    with pytest.raises(ImproperlyConfigured):
        verify_admission_configuration()
