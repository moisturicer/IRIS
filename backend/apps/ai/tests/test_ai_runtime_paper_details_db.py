"""A paper's recorded details, on real PostgreSQL (IR-1278, ADR-049 §5, §9).

Driven through the run routes with a scripted executor calling the tools,
under the restricted `iris_ai_runtime` login and Django-issued grants, so what
a reader gets is the row policy's answer, not the tool's.
"""

import asyncio
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[4]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from ai.research.tools import PaperDetails  # noqa: E402

from apps.records.models import Author, Classification, PSCEDClassification, Record, RecordType  # noqa: E402
from core.enums import PipelineStatus  # noqa: E402
from .corpus import make_user  # noqa: E402
from . import test_ai_runtime_runs_db as runs_db  # noqa: E402
from .test_ai_runtime_metadata_db import bare  # noqa: E402
from .test_ai_runtime_research_db import FLOOD, ask, paper  # noqa: E402

api = runs_db.api
runtime = runs_db.runtime

pytestmark = [pytest.mark.db_required, pytest.mark.django_db(transaction=True)]


@pytest.fixture
def research(api, runtime):
    client, holder = api
    holder["dsn"] = runtime
    return api


def described(record, *, adviser=None, authors=(), **fields):
    """`record` with what the Publish form records filled in."""
    Record.objects.filter(pk=record.pk).update(adviser=adviser, **fields)
    for name in authors:
        Author.objects.create(record=record, name=name)
    record.refresh_from_db()
    return record


def test_a_reader_gets_everything_the_publish_form_recorded(research):
    reader = make_user("details-reader@cit.edu")
    adviser = make_user("details-adviser@cit.edu")
    adviser.first_name, adviser.middle_initial, adviser.last_name = "Carla", "M.", "Santos"
    adviser.save(update_fields=["first_name", "middle_initial", "last_name"])
    flood = described(
        paper("Flood forecasting", {4: [("Methods", FLOOD)]}),
        adviser=adviser, authors=("Ana Cruz", "Ben Reyes"),
        year_completed=2023, year_accomplished=2022, publication_year=2024,
        classification=Classification.objects.create(name="Hydrology"),
        psced=PSCEDClassification.objects.create(name="Engineering and engineering trades"),
        record_type=RecordType.objects.get_or_create(name="Thesis / Research")[0],
        keywords=["floods", "neural networks"], abstract="We predicted 87 floods from 12 gauges.",
        origin=Record.Origin.INSTITUTIONAL, for_commercialization=True, requested_ktto=True,
    )

    async def script(tools):
        named = await tools.resolve([], record_ids=[flood.pk])
        await tools.details([named.matches[0].records[0].handle])

    response, seen, _ = ask(research, reader, script, key="details-all")
    assert response.json()["state"] == "completed"
    (_, named), (_, found) = seen
    handle = named.matches[0].records[0].handle
    assert found.status == "ok" and (found.coverage.returned, found.coverage.total) == (1, 1)
    assert found.details == (PaperDetails(
        handle=handle, record_id=flood.pk, title="Flood forecasting",
        authors=("Ana Cruz", "Ben Reyes"), adviser="Carla M. Santos",
        year_completed=2023, year_accomplished=2022, publication_year=2024,
        record_type="Thesis / Research", classification="Hydrology",
        psced="Engineering and engineering trades", keywords=("floods", "neural networks"),
        abstract="We predicted 87 floods from 12 gauges.", origin="institutional",
        is_ip=False, ip_type=None, for_commercialization=True, community_extension=False,
        requires_ethics_review=False, requested_offices=("KTTO",),
    ),)
    # A name, never the account behind it.
    assert adviser.email not in repr(found)


def test_a_deleted_advisers_kept_name_is_returned_and_an_unrecorded_detail_is_none(research):
    reader = make_user("details-kept@cit.edu")
    record = described(bare("Coastal erosion survey"), adviser_name="Dana Lim")

    async def script(tools):
        named = await tools.resolve([], record_ids=[record.pk])
        await tools.details([named.matches[0].records[0].handle])

    _, seen, _ = ask(research, reader, script, key="details-kept")
    (_, _), (_, found) = seen
    (details,) = found.details
    assert details.adviser == "Dana Lim"
    assert (details.authors, details.year_completed, details.keywords, details.abstract) == ((), None, (), "")


def test_a_paper_the_reader_loses_is_an_unknown_handle_and_the_rest_still_read(research):
    reader = make_user("details-revoked@cit.edu")
    kept = bare("Flood gauges")
    revoked = described(bare("River sediment"), authors=("Hidden Author",))

    def unpublish():
        Record.objects.filter(pk=revoked.pk).update(pipeline_status=PipelineStatus.DRAFT)

    async def script(tools):
        named = await tools.resolve([], record_ids=[kept.pk, revoked.pk])
        handles = [m.records[0].handle for m in named.matches]
        await asyncio.to_thread(unpublish)
        await tools.details(handles)
        await tools.details(handles[1:])
        await tools.details(["R" + "0" * 20])

    _, seen, _ = ask(research, reader, script, key="details-revoked")
    (_, _), (_, partial), (_, gone), (_, never) = seen
    assert partial.status == "partial" and [d.record_id for d in partial.details] == [kept.pk]
    assert (partial.coverage.returned, partial.coverage.total) == (1, 2)
    # Lost and never issued read the same: nothing says the paper exists.
    assert (gone.status, gone.reason, gone.details) == ("unavailable", "unknown_handle", ())
    assert (never.status, never.reason, never.details) == ("unavailable", "unknown_handle", ())
    assert "Hidden Author" not in repr(partial)


def test_an_owners_own_paper_embargoed_mid_run_is_an_unknown_handle_to_its_owner(research):
    owner = make_user("details-embargo-owner@cit.edu")
    mine = described(bare("Mangrove survey", owner=owner), authors=("Owner Author",))

    def embargo():
        # Embargoed again: no release stamp, as the constraint requires (ADR-052).
        Record.objects.filter(pk=mine.pk).update(is_embargoed=True, embargo_released_at=None)

    async def script(tools):
        named = await tools.resolve([], record_ids=[mine.pk])
        handle = named.matches[0].records[0].handle
        await tools.details([handle])
        await asyncio.to_thread(embargo)
        await tools.details([handle])

    _, seen, _ = ask(research, owner, script, key="details-embargo-owner")
    (_, _), (_, before), (_, after) = seen
    assert [d.authors for d in before.details] == [("Owner Author",)]
    # Its own owner is held to the disclosure gate like any reader (IR-1252).
    assert (after.status, after.reason, after.details) == ("unavailable", "unknown_handle", ())


def test_paper_chat_reads_only_its_own_papers_details(research):
    reader = make_user("details-scope@cit.edu")
    scoped = described(paper("Flood forecasting", {4: [("Methods", FLOOD)]}), authors=("Ana Cruz",))
    other = described(bare("Flood risk maps"), authors=("Someone Else",))

    async def script(tools):
        named = await tools.resolve([], record_ids=[scoped.pk, other.pk])
        await tools.details([m.records[0].handle for m in named.matches if m.records])

    _, seen, _ = ask(research, reader, script, key="details-scope", record_id=scoped.pk)
    (_, named), (_, found) = seen
    assert [m.match for m in named.matches] == ["record_id", "none"]
    assert [(d.record_id, d.authors) for d in found.details] == [(scoped.pk, ("Ana Cruz",))]


def test_the_adviser_function_answers_only_for_papers_the_grant_may_read(research):
    owner, reader = make_user("details-owner@cit.edu"), make_user("details-stranger@cit.edu")
    adviser = make_user("details-adviser2@cit.edu")
    adviser.first_name, adviser.last_name = "Eli", "Tan"
    adviser.save(update_fields=["first_name", "last_name"])
    published = described(bare("Published study"), adviser=adviser)
    draft = described(bare("Private study", status=PipelineStatus.DRAFT, owner=owner), adviser=adviser)
    names = []

    async def script(tools):
        # Called directly, as a runtime login could, with ids it was never given a handle for.
        async with tools._tools._session() as conn:
            names.extend(await conn.fetch(
                "SELECT record_id, name FROM iris_authz.research_advisers($1::bigint[]) ORDER BY record_id",
                [published.pk, draft.pk]))

    ask(research, reader, script, key="details-fn-stranger")
    assert [tuple(row) for row in names] == [(published.pk, "Eli Tan")]
    # The draft's own owner is told nothing either: a draft never reaches the AI (IR-1252).
    names.clear()
    ask(research, owner, script, key="details-fn-owner")
    assert [tuple(row) for row in names] == [(published.pk, "Eli Tan")]
