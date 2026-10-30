"""Migrate populated historical records without manufacturing provenance."""
import pytest
from django.core.management import call_command
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from apps.accounts.models import User

pytestmark = [pytest.mark.db_required, pytest.mark.django_db(transaction=True)]


def test_existing_research_keeps_authors_owners_completion_and_workflow():
    before = [("records", "0020_record_derived_from")]
    executor = MigrationExecutor(connection)
    executor.migrate(before)
    try:
        apps = executor.loader.project_state(before).apps
        Record = apps.get_model("records", "Record")
        Author = apps.get_model("records", "Author")
        Owner = apps.get_model("records", "RecordOwner")
        actor = User.objects.create(email="historical-importer@cit.edu", password="!")
        ids = []
        for title, status, names in [
            ("Attention Is All You Need", "published", ["Ashish Vaswani", "Noam Shazeer"]),
            ("Legacy CIT-U study", "published", []),
            ("Demonstration proposal", "draft", ["Recorded Example"]),
        ]:
            record = Record.objects.create(title=title, pipeline_status=status, added_by_id=actor.pk,
                                           year_accomplished=2020, year_completed=2021)
            Owner.objects.create(record=record, user_id=actor.pk, is_primary=True)
            for name in names:
                Author.objects.create(record=record, name=name)
            ids.append((record.pk, status, names))
        after = [("records", "0021_record_research_metadata")]
        executor = MigrationExecutor(connection)
        executor.migrate(after)
        Record = executor.loader.project_state(after).apps.get_model("records", "Record")
        for pk, status, names in ids:
            record = Record.objects.get(pk=pk)
            assert (record.origin, record.publication_year) == ("unknown", None)
            assert (record.year_accomplished, record.year_completed, record.pipeline_status) == (2020, 2021, status)
            assert list(record.authors.order_by("pk").values_list("name", flat=True)) == names
            assert record.owners.get().user_id == actor.pk
            assert record.added_by_id == actor.pk
    finally:
        call_command("migrate", verbosity=0)
