"""The raw result stays out of the API; the admin shows its pages (IR-841)."""

import pytest

pytestmark = [pytest.mark.django_required]


def test_the_raw_result_never_reaches_the_api():
    from apps.documents.serializers import PdfExtractionSerializer

    exposed = set(PdfExtractionSerializer.Meta.fields)

    assert not exposed & {"raw_result", "credits", "pages_read", "warnings"}


def test_the_admin_shows_the_page_report():
    from apps.documents.admin import PdfExtractionAdmin
    from apps.documents.models import PdfExtraction

    row = PdfExtraction(raw_result={"metadata": {"pages": [{"page_number": 1, "confidence": 0.2}]}})

    assert PdfExtractionAdmin.pages(None, row) == "p1: 0.20 LOW"
