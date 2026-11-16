"""Unstructured's extraction price: flat US$ per page, never defaulted (IR-983)."""

from decimal import Decimal

import pytest
from django.core.exceptions import ImproperlyConfigured

from apps.ai.admission.limits import (
    EXTRACTION_SETTINGS,
    NotConfigured,
    read_extraction_price,
    verify_admission_configuration,
)

from .support import enforce

pytestmark = pytest.mark.django_required

NAME = "AI_ADMISSION_EXTRACTION_UNSTRUCTURED_USD_PER_PAGE"


def test_unstructured_is_one_credit_a_page_at_its_usd_price(settings):
    enforce(settings, **{NAME: "0.01"})
    price = read_extraction_price()
    assert (price.credit_usd, price.credits_per_page, price.addon_credits_per_page) == (
        Decimal("0.01"), Decimal(1), Decimal(0),
    )
    assert price.reserve_micros(7) == 70_000


def test_an_unset_unstructured_price_is_not_configured_and_never_defaulted(settings):
    enforce(settings, **{NAME: ""})
    with pytest.raises(NotConfigured, match=NAME):
        read_extraction_price()
    verify_admission_configuration()


def test_unstructureds_is_the_only_extraction_price():
    assert EXTRACTION_SETTINGS == (NAME,)


@pytest.mark.parametrize("value", ["free", "0", "-0.01", "NaN"])
def test_a_malformed_unstructured_price_stops_startup(settings, value):
    enforce(settings, **{NAME: value})
    with pytest.raises(ImproperlyConfigured):
        verify_admission_configuration()
