"""An enriched Unstructured read stores each Figure's description (IR-1126),
so the describer sends nothing for it and the chunker embeds it unchanged."""

import pytest

from apps.ai import tasks as ai_tasks
from apps.ai.extraction import use_extractor
from apps.ai.extraction.shaping_unstructured import shape_unstructured
from apps.ai.extraction.tests.test_unstructured_image_descriptions import DESCRIPTION, enriched
from apps.ai.extraction.tests.test_unstructured_figures import caption
from apps.ai.extraction.tests.unstructured_platform_vendor import API_KEY, Vendor, recording
from apps.ai.extraction.unstructured_client import UnstructuredExtractor
from apps.ai.figure_descriptions import describe_figures
from apps.ai.tests.test_figure_descriptions import Describer, figure_chunks, root
from apps.documents import tasks
from apps.documents.tests.test_unstructured_figure_storage import Ungated, _record
from apps.records.tests import make_user
from core.enums import RoleName

pytestmark = [pytest.mark.db_required, pytest.mark.django_db]


@pytest.fixture(autouse=True)
def no_followups(monkeypatch):
    monkeypatch.setattr(tasks, "_queue_chunk_extraction", lambda *args, **kwargs: None)
    monkeypatch.setattr(ai_tasks.embed_chunk_set, "delay", lambda *a, **k: None)
    monkeypatch.setattr("apps.ai.overview.service.queue_overview_for_chunk_set", lambda *a, **k: None)
    monkeypatch.setattr("apps.ai.figure_descriptions._queue_rechunk", lambda *a, **k: None)


def _read(record, *, describe_images):
    elements = recording("figures")
    elements[3:3] = [enriched("img-1"), caption("Figure 1: Accuracy.")]
    adapter = UnstructuredExtractor(api=Vendor("figures", result=elements).api(), api_key=API_KEY,
                                    shape=shape_unstructured, sleep=lambda seconds: None,
                                    describe_images=describe_images)
    with use_extractor(Ungated(adapter)):
        tasks.extract_manuscript_text.apply(args=[record.id, str(record.manuscript_revision)])


def test_an_enriched_figure_is_stored_described_and_not_sent_to_the_describer():
    record, extraction = _record(make_user("ir1126-owner@cit.edu", RoleName.STUDENT))

    _read(record, describe_images=True)

    (figure,) = extraction.figures.all()
    assert figure.description == DESCRIPTION
    describer = Describer()
    with root(describer):
        assert describe_figures(extraction.pk, record.manuscript_revision) == 0
    assert describer.images == []


def test_with_the_switch_off_the_figure_is_stored_undescribed_and_still_sent():
    record, extraction = _record(make_user("ir1126-off@cit.edu", RoleName.STUDENT))

    _read(record, describe_images=False)

    (figure,) = extraction.figures.all()
    assert figure.description == ""
    describer = Describer()
    with root(describer):
        assert describe_figures(extraction.pk, record.manuscript_revision) == 1
    assert len(describer.images) == 1


def test_the_chunker_embeds_the_enrichments_description_but_never_shows_it():
    record, extraction = _record(make_user("ir1126-chunk@cit.edu", RoleName.STUDENT))
    _read(record, describe_images=True)

    ai_tasks.chunk_extraction.apply(args=[extraction.pk, str(record.manuscript_revision)]).get()

    chunks = figure_chunks(record)
    assert [c for c in chunks if DESCRIPTION in c.text]
    assert all(DESCRIPTION not in c.content for c in chunks)
