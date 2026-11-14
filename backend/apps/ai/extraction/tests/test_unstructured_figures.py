"""Figures from Unstructured's ``image_base64`` (IR-987, ADR-067 decision 10).

The ``figures`` recording found no Image on its vector-drawn shapes, so these
tests add Image elements in the shape the amended spike recorded (ADR-067,
2026-11-14 amendment §4). The recording itself is not edited.
"""

import base64
from io import BytesIO

import pytest
from PIL import Image

from apps.ai.extraction.shaping_unstructured import shape_unstructured
from apps.ai.extraction.unstructured_client import UnstructuredExtractor

from .fixtures import FIXTURES, pdf_bytes
from .unstructured_platform_vendor import API_KEY, Vendor, recording

# hi_res's US Letter page in pixels.
LAYOUT = {"layout_width": 2125, "layout_height": 2750, "system": "PixelSpace"}


def png(width=4, height=3) -> bytes:
    out = BytesIO()
    Image.new("RGB", (width, height), "white").save(out, format="PNG")
    return out.getvalue()


def image(element_id, data, *, page=1, mime="image/png", points=((250, 500), (250, 1000), (1000, 1000), (1000, 500))):
    return {
        "type": "Image", "element_id": element_id, "text": "OCR noise",
        "metadata": {
            "page_number": page, "image_base64": base64.b64encode(data).decode(),
            "image_mime_type": mime, "coordinates": {"points": [list(p) for p in points], **LAYOUT},
        },
    }


def caption(text, *, page=1):
    return {"type": "FigureCaption", "element_id": f"cap-{text[:6]}", "text": text,
            "metadata": {"page_number": page}}


def read(extra, **overrides):
    elements = recording("figures")
    elements[3:3] = extra
    options = dict(api=Vendor("figures", result=elements).api(), api_key=API_KEY,
                   shape=shape_unstructured, sleep=lambda seconds: None)
    options.update(overrides)
    fixture = FIXTURES["figures"]
    return UnstructuredExtractor(**options).extract(pdf_bytes(fixture), filename=fixture.filename)


def test_an_image_element_becomes_a_figure_with_its_page_box_caption_and_name():
    data = png()

    extracted = read([image("img-1", data), caption("Figure 1: A captioned rectangle.")])

    (figure,) = extracted.figures
    assert figure.data == data
    assert figure.media_type == "image/png"
    assert figure.page == 1
    assert figure.caption == "Figure 1: A captioned rectangle."
    # 250 dpi pixels to page points: 250 px is 72 pt.
    assert figure.bbox == pytest.approx({"x": 72.0, "y": 144.0, "w": 216.0, "h": 144.0})
    assert figure.name == "img-1"
    (element,) = [e for e in extracted.document.elements if e.figure == "img-1"]
    assert element.kind == "image"


def test_an_uncaptioned_image_is_kept_without_a_caption():
    (figure,) = read([image("img-1", png())]).figures

    assert figure.caption is None


def test_a_jpeg_keeps_the_vendors_media_type():
    out = BytesIO()
    Image.new("RGB", (4, 3)).save(out, format="JPEG")

    (figure,) = read([image("img-1", out.getvalue(), mime="image/jpeg")]).figures

    assert figure.media_type == "image/jpeg"
    assert figure.data.startswith(b"\xff\xd8\xff")


def test_figures_past_the_per_document_bound_are_not_kept():
    extra = [image(f"img-{n}", png()) for n in range(3)]

    figures = read(extra, max_figures=2).figures

    assert [f.name for f in figures] == ["img-0", "img-1"]


def test_an_image_over_the_per_figure_pixel_bound_is_not_kept():
    extra = [image("big", png(10, 10)), image("small", png(9, 11))]

    figures = read(extra, max_figure_pixels=99).figures

    assert [f.name for f in figures] == ["small"]


def test_bytes_that_are_not_an_image_are_not_kept():
    broken = image("broken", b"")
    broken["metadata"]["image_base64"] = "not base64!"
    extra = [broken, image("html", b"<html><script>alert(1)</script>"), image("ok", png())]

    assert [f.name for f in read(extra).figures] == ["ok"]


def test_a_table_image_is_not_a_figure():
    table = image("tbl", png())
    table.update(type="Table", text="a | b")

    assert read([table]).figures == ()


def test_the_builder_passes_both_bounds(settings):
    from apps.ai.extraction.selection import unstructured_extractor

    settings.UNSTRUCTURED_PLATFORM_API_KEY = "configured"
    settings.UNSTRUCTURED_BASE_URL = "https://api.unstructuredapp.io"
    settings.UNSTRUCTURED_MAX_FIGURES = 1
    settings.UNSTRUCTURED_MAX_FIGURE_PIXELS = 99

    adapter = unstructured_extractor()
    elements = recording("figures")
    elements[3:3] = [image("big", png(10, 10)), image("a", png()), image("b", png())]
    adapter._api = Vendor("figures", result=elements).api()
    fixture = FIXTURES["figures"]

    figures = adapter.extract(pdf_bytes(fixture), filename=fixture.filename).figures

    assert [f.name for f in figures] == ["a"]


def test_an_image_that_is_not_its_stated_type_takes_no_slot_under_the_bound():
    extra = [image("mislabelled", png(), mime="image/jpeg"), image("ok", png())]

    assert [f.name for f in read(extra, max_figures=1).figures] == ["ok"]
