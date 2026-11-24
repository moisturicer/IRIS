"""Random years for test papers only (IR-1316)."""

from io import StringIO

import pytest
from django.core.management import CommandError, call_command

from apps.accounts.models import User
from apps.records.models import Record
from core.enums import PipelineStatus

pytestmark = [pytest.mark.db_required, pytest.mark.django_db]
LOADER = "corpus-loader@cit.edu"


@pytest.fixture(autouse=True)
def development(settings):
    settings.DEBUG = True


@pytest.fixture
def loader():
    return User.objects.create_user(email=LOADER, password="x", first_name="Corpus", last_name="Loader")


def paper(owner, **fields):
    fields = {"origin": Record.Origin.IMPORTED_REFERENCE, "pipeline_status": PipelineStatus.PUBLISHED, **fields}
    return Record.objects.create(added_by=owner, title="Test paper", abstract="", **fields)


def years(record):
    record.refresh_from_db()
    return record.year_accomplished, record.year_completed, record.publication_year


def fill(**options):
    out = StringIO()
    call_command("fill_test_years", stdout=out, **options)
    return out.getvalue()


def test_blank_years_are_filled_the_same_way_every_time_and_undo_blanks_them(loader):
    record = paper(loader)
    fill()
    first = years(record)
    completed, _, published = first
    assert 2015 <= completed <= published <= 2026
    fill()
    assert years(record) == first
    fill(undo=True)
    assert years(record) == (None, None, None)
    fill()
    assert years(record) == first


def test_a_recorded_year_is_never_overwritten_or_undone(loader):
    kept = paper(loader, year_accomplished=1999, publication_year=2001)
    imported = paper(loader, year_completed=1998, publication_year=2000)
    fill()
    fill(undo=True)
    assert years(kept) == (1999, None, 2001)
    assert years(imported) == (None, 1998, 2000)


def test_only_the_loaders_published_test_papers_are_touched(loader):
    other = User.objects.create_user(email="someone@cit.edu", password="x", first_name="Some", last_name="One")
    untouched = [
        paper(other), paper(loader, pipeline_status=PipelineStatus.IN_REVIEW),
        paper(loader, pipeline_status=PipelineStatus.DRAFT), paper(loader, origin=Record.Origin.INSTITUTIONAL),
        paper(loader, origin=Record.Origin.UNKNOWN),
    ]
    assert "Changed 0 of 0" in fill()
    assert [years(r) for r in untouched] == [(None, None, None)] * len(untouched)


def test_a_dry_run_writes_nothing_and_it_refuses_outside_development(loader, settings):
    record = paper(loader)
    assert "Would change 1 of 1" in fill(dry_run=True)
    assert years(record) == (None, None, None)
    settings.DEBUG = False
    with pytest.raises(CommandError):
        fill()
    assert years(record) == (None, None, None)
