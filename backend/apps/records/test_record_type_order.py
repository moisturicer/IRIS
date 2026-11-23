"""Record types keep one order wherever they are listed (IR-1277).

`RecordType` had no ordering, so the database returned types in storage order.
Updating a row stores a new copy of it at the end, so a type RDCO saved on
Setup moved to the end of Publish's choices. These pin the workflow order:
Proposal, Thesis / Research, Project, then any other type, oldest first.
"""

import pytest
from django.core.management import call_command
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from rest_framework.test import APIClient

from apps.accounts.models import Role, User
from apps.records.models import RecordType
from core.enums import RecordTypeName

pytestmark = pytest.mark.db_required

WORKFLOW = [RecordTypeName.PROPOSAL, RecordTypeName.THESIS_RESEARCH, RecordTypeName.PROJECT]


def _signed_in(role="Student"):
    user = User.objects.create_user(
        email=f"order-{role.lower()}@cit.edu", password="TestPass123!", is_verified=True,
        first_name="Order", last_name=role, role=Role.objects.get_or_create(name=role)[0],
    )
    client = APIClient()
    client.force_authenticate(user)
    return client


def _publish_names(client):
    response = client.get("/api/v1/records/record-types/")
    assert response.status_code == 200, response.data
    return [row["name"] for row in response.data["results"]]


@pytest.mark.django_db
def test_publish_lists_the_types_in_workflow_order_after_any_is_saved():
    client = _signed_in()
    assert _publish_names(client) == WORKFLOW

    # Saving rewrites the row, which is what moved a type to the end before.
    for name in reversed(WORKFLOW):
        record_type = RecordType.objects.get(name=name)
        record_type.description = f"Saved on Setup: {name}"
        record_type.save()

    assert _publish_names(client) == WORKFLOW


@pytest.mark.django_db
def test_setup_and_guidelines_list_the_same_order():
    RecordType.objects.get(name=RecordTypeName.PROPOSAL).save()

    setup = _signed_in("RDCO").get("/api/v1/documents/setup/record-types/")
    assert setup.status_code == 200, setup.data
    assert [row["name"] for row in setup.data] == WORKFLOW

    assert [rt.name for rt in RecordType.objects.all()] == WORKFLOW


@pytest.mark.django_db
def test_another_type_comes_after_the_workflow_types():
    RecordType.objects.create(name="Capstone Report")

    assert _publish_names(_signed_in()) == [*WORKFLOW, "Capstone Report"]


@pytest.mark.django_db(transaction=True)
@pytest.mark.slow
def test_0044_numbers_the_types_by_name_not_by_id():
    """An older database's ids need not follow the workflow order (records/0006)."""
    before, after = [("records", "0043_setup_requirements")], [("records", "0044_recordtype_position")]
    executor = MigrationExecutor(connection)
    executor.migrate(before)
    try:
        old = MigrationExecutor(connection).loader.project_state(before).apps.get_model("records", "RecordType")
        # Recreate the three types newest-first, so id order is the reverse of the workflow.
        rows = {row.name: row for row in old.objects.filter(name__in=WORKFLOW)}
        for name in reversed(WORKFLOW):
            rows[name].name = f"{name} (old)"
            rows[name].save()
            old.objects.create(name=name)
        old.objects.filter(name__endswith=" (old)").delete()

        MigrationExecutor(connection).migrate(after)
        new = MigrationExecutor(connection).loader.project_state(after).apps.get_model("records", "RecordType")

        assert [rt.name for rt in new.objects.filter(name__in=WORKFLOW).order_by("pk")] == WORKFLOW[::-1]
        assert [rt.name for rt in new.objects.filter(name__in=WORKFLOW)] == WORKFLOW
    finally:
        call_command("migrate", verbosity=0)
