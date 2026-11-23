"""The three dates of published papers, on real PostgreSQL (IR-1316, ADR-049 §5, §9).

Driven through the run routes under the restricted `iris_ai_runtime` login and
Django-issued grants, so what a reader gets is the row policy's answer.
"""

import sys
from datetime import date, datetime, timezone
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[4]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from apps.records.models import Record  # noqa: E402
from core.enums import PipelineStatus  # noqa: E402
from .corpus import make_user  # noqa: E402
from . import test_ai_runtime_runs_db as runs_db  # noqa: E402
from .test_ai_runtime_metadata_db import area, bare  # noqa: E402
from .test_ai_runtime_research_db import FLOOD, ask, paper  # noqa: E402

api = runs_db.api
runtime = runs_db.runtime

pytestmark = [pytest.mark.db_required, pytest.mark.django_db(transaction=True)]


@pytest.fixture
def research(api, runtime):
    client, holder = api
    holder["dsn"] = runtime
    return api


def added(record, when):
    Record.objects.filter(pk=record.pk).update(created_at=when)
    return record


def utc(*when):
    return datetime(*when, tzinfo=timezone.utc)


def titles(result):
    return [r.title for r in result.records]


def test_completion_year_is_the_forms_else_an_imports(research):
    reader = make_user("recent-year@cit.edu")
    bare("Form", year_accomplished=2024)
    bare("Import", year_completed=2023)
    bare("Both", year_accomplished=2020, year_completed=2025)
    bare("Neither")

    async def script(tools):
        await tools.list_records({"year_from": 2022})
        await tools.count({"year_from": 2022})
        await tools.count({}, "year")
        await tools.list_records({}, sort="completed")

    _, seen, _ = ask(research, reader, script, key="recent-year")
    (_, listed), (_, counted), (_, grouped), (_, newest) = seen
    assert [(r.title, r.year) for r in listed.records] == [("Form", 2024), ("Import", 2023)]
    # The one paper with no year is reported, not silently dropped.
    assert (counted.count.total, counted.count.undated, listed.count.undated) == (2, 1, 1)
    assert grouped.count.groups == ((2020, 1), (2023, 1), (2024, 1)) and grouped.count.ungrouped == 1
    assert titles(newest) == ["Form", "Import", "Both", "Neither"]


def test_papers_filter_sort_and_group_by_publication_year(research):
    reader = make_user("recent-published@cit.edu")
    hydrology = area("Hydrology")
    bare("Older", publication_year=2019, classification=hydrology)
    bare("Newer", publication_year=2025, classification=hydrology)
    bare("Unpublished elsewhere", classification=hydrology)
    bare("Other area", publication_year=2026)

    async def script(tools):
        await tools.list_records({"published_from": 2020, "classification": "Hydrology"})
        await tools.list_records({"classification": "Hydrology"}, sort="published")
        await tools.count({}, "publication_year")

    _, seen, _ = ask(research, reader, script, key="recent-published")
    (_, ranged), (_, newest), (_, grouped) = seen
    assert titles(ranged) == ["Newer"] and ranged.count.undated == 1
    assert ranged.count.filters == (("classification", "Hydrology"), ("published_from", 2020))
    assert titles(newest) == ["Newer", "Older", "Unpublished elsewhere"]
    assert grouped.count.groups == ((2019, 1), (2025, 1), (2026, 1)) and grouped.count.ungrouped == 1


def test_papers_filter_and_sort_by_the_campus_day_they_were_added(research):
    reader = make_user("recent-added@cit.edu")
    added(bare("Late"), utc(2026, 8, 25, 17))     # 26 August, 1 a.m. in Cebu
    added(bare("Early"), utc(2026, 8, 25, 15))    # 25 August, 11 p.m. in Cebu
    added(bare("Newest"), utc(2026, 10, 5, 3))

    async def script(tools):
        await tools.list_records({"added_from": "2026-08-26"}, sort="added")
        await tools.list_records({"added_from": "2026-08-25", "added_to": "2026-08-25"})
        await tools.list_records({"added_from": "soon"})

    _, seen, _ = ask(research, reader, script, key="recent-added")
    (_, since), (_, one_day), (_, bad) = seen
    assert [(r.title, r.added) for r in since.records] == [
        ("Newest", date(2026, 10, 5)), ("Late", date(2026, 8, 26))]
    assert titles(one_day) == ["Early"]
    assert (bad.status, bad.reason) == ("unavailable", "invalid_argument")


def test_search_narrows_by_every_date_and_returns_them(research):
    reader = make_user("recent-search@cit.edu")
    old, new = (paper(title, {4: [("Methods", FLOOD)]}) for title in ("Old floods", "New floods"))
    Record.objects.filter(pk=old.pk).update(year_accomplished=2016, publication_year=2017, created_at=utc(2025, 1, 2))
    Record.objects.filter(pk=new.pk).update(year_accomplished=2024, publication_year=2025, created_at=utc(2026, 10, 5))
    query = "neural network rainfall"

    async def script(tools):
        for filters in ({}, {"year_from": 2022}, {"published_from": 2022}, {"added_from": "2026-08-26"}):
            await tools.hybrid_search(query, 10, filters)

    _, seen, _ = ask(research, reader, script, key="recent-search")
    (_, every), *narrowed = seen
    assert {(r.title, r.year, r.publication_year, r.added) for r in every.records} == {
        ("Old floods", 2016, 2017, date(2025, 1, 2)), ("New floods", 2024, 2025, date(2026, 10, 5))}
    assert [titles(result) for _, result in narrowed] == [["New floods"]] * 3


@pytest.mark.parametrize("status", [PipelineStatus.DRAFT, PipelineStatus.IN_REVIEW, PipelineStatus.APPROVED])
def test_a_paper_not_yet_published_gives_no_date_to_anyone_even_its_owner(research, status):
    owner = make_user(f"recent-{status}@cit.edu")
    unpublished = bare("Unpublished", status=status, owner=owner, year_accomplished=2026, publication_year=2026)
    bare("Published", year_accomplished=2025)

    async def script(tools):
        await tools.list_records({}, sort="added")
        await tools.list_records({"year_from": 2022})
        await tools.count({"published_from": 2022})
        await tools.resolve([], record_ids=[unpublished.pk])

    _, seen, _ = ask(research, owner, script, key=f"recent-{status}")
    (_, newest), (_, ranged), (_, counted), (_, named) = seen
    assert titles(newest) == titles(ranged) == ["Published"]
    # Not in the total, nor among the papers left out for having no year.
    assert (counted.count.total, counted.count.undated) == (0, 1)
    assert named.matches[0].match == "none"


def test_paper_details_carry_the_date_added(research):
    reader = make_user("recent-details@cit.edu")
    record = added(bare("Dated", year_completed=2021, year_accomplished=2022), utc(2026, 10, 5, 3))

    async def script(tools):
        named = await tools.resolve([], record_ids=[record.pk])
        await tools.details([named.matches[0].records[0].handle])

    _, seen, _ = ask(research, reader, script, key="recent-details")
    (_, _), (_, found) = seen
    (details,) = found.details
    assert (details.completion_year, details.date_added) == (2022, date(2026, 10, 5))
