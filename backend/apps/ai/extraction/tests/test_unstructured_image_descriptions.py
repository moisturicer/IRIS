"""Unstructured's image-description enrichment, behind a switch (IR-1126).

The enrichment replaces an Image element's ``text`` with a JSON string carrying
``type`` and ``description`` (Unstructured, ``concepts/enriching/image-descriptions``).
Whether the partition endpoint accepts it is IR-1126's spike; these tests use
the documented shape.
"""

import json
import re

import pytest
from django.test import override_settings

from apps.ai.extraction.selection import unstructured_extractor
from apps.ai.extraction.shaping_unstructured import shape_unstructured
from apps.ai.extraction.unstructured_client import (
    IMAGE_DESCRIPTION_OPTIONS,
    REQUEST_OPTIONS,
    UnstructuredExtractor,
)

from .fixtures import FIXTURES, pdf_bytes
from .test_unstructured_figures import caption, image, png
from .unstructured_platform_vendor import API_KEY, Vendor, recording

DESCRIPTION = "A line graph of accuracy against epochs, rising from 0.6 to 0.9."


def described(element_id, text):
    element = image(element_id, png())
    element["text"] = text
    return element


def enriched(element_id, description=DESCRIPTION):
    return described(element_id, json.dumps({"type": "graph", "description": description}))


def read(extra, **overrides):
    elements = recording("figures")
    elements[3:3] = extra
    vendor = Vendor("figures", result=elements)
    options = dict(api=vendor.api(), api_key=API_KEY, shape=shape_unstructured, sleep=lambda seconds: None)
    options.update(overrides)
    fixture = FIXTURES["figures"]
    extracted = UnstructuredExtractor(**options).extract(pdf_bytes(fixture), filename=fixture.filename)
    return extracted, vendor


def form_fields(vendor) -> set[str]:
    return {name.decode() for name in re.findall(rb'; name="([^"]+)"', vendor.form())}


def test_off_by_default_the_request_and_the_figure_are_unchanged():
    extracted, vendor = read([enriched("img-1"), caption("Figure 1: Accuracy.")])

    assert form_fields(vendor) == set(REQUEST_OPTIONS) | {"files"}
    (figure,) = extracted.figures
    assert figure.description == ""
    assert "call" in extracted.provenance.options
    assert set(extracted.provenance.options) == set(REQUEST_OPTIONS) | {"call"}


def test_on_the_request_asks_for_the_enrichment_and_provenance_records_it():
    extracted, vendor = read([enriched("img-1")], describe_images=True)

    assert form_fields(vendor) == set(REQUEST_OPTIONS) | set(IMAGE_DESCRIPTION_OPTIONS) | {"files"}
    for key, value in IMAGE_DESCRIPTION_OPTIONS.items():
        assert extracted.provenance.options[key] == value


def test_on_the_description_joins_its_figure_by_element_and_never_reaches_content():
    extracted, _ = read([enriched("img-1"), caption("Figure 1: Accuracy.")], describe_images=True)

    (figure,) = extracted.figures
    assert figure.name == "img-1"
    assert figure.description == DESCRIPTION
    assert figure.caption == "Figure 1: Accuracy."
    assert all(DESCRIPTION not in (e.text or "") for e in extracted.document.elements)


@pytest.mark.parametrize("text", [
    "OCR noise",
    json.dumps({"type": "graph"}),
    json.dumps({"type": "graph", "description": "   "}),
    json.dumps({"type": "graph", "description": 42}),
    json.dumps(["not", "an", "object"]),
])
def test_on_an_image_with_no_usable_description_is_left_for_the_describer(text):
    extracted, _ = read([described("img-1", text)], describe_images=True)

    (figure,) = extracted.figures
    assert figure.description == ""


@override_settings(UNSTRUCTURED_PLATFORM_API_KEY="key", UNSTRUCTURED_BASE_URL="https://api.unstructuredapp.io")
@pytest.mark.parametrize("switch", [False, True])
def test_the_setting_is_the_switch(switch):
    with override_settings(UNSTRUCTURED_IMAGE_DESCRIPTIONS=switch):
        assert unstructured_extractor().describes_images is switch
