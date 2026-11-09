"""Django's research reads through the one database policy, behind a default-off switch (IR-718)."""

import pytest
from django.core.exceptions import ImproperlyConfigured

from apps.ai.grants import reads
from apps.records.models import Record, RecordOwner
from core.enums import PipelineStatus
from core.permissions import ROLE_ADVISER, ROLE_RDCO, ROLE_STUDENT
from .corpus import make_user
from .grant_support import (
    drop_research_alias, probe_credentials, use_research_alias,
)

pytestmark = [pytest.mark.db_required, pytest.mark.django_db(transaction=True)]


@pytest.fixture(autouse=True)
def _no_research_alias_left_behind():
    yield
    drop_research_alias()


@pytest.fixture
def people():
    owner = make_user("reads-owner@cit.edu", ROLE_STUDENT)
    adviser = make_user("reads-adviser@cit.edu", ROLE_ADVISER)
    office = make_user("reads-office@cit.edu", ROLE_RDCO)
    stranger = make_user("reads-stranger@cit.edu", ROLE_STUDENT)
    Record.objects.create(title="Published", abstract="a", pipeline_status=PipelineStatus.PUBLISHED)
    draft = Record.objects.create(title="Draft", abstract="a", pipeline_status=PipelineStatus.DRAFT,
                                  adviser=adviser)
    RecordOwner.objects.create(record=draft, user=owner, is_primary=True)
    Record.objects.create(title="Other draft", abstract="a", pipeline_status=PipelineStatus.DRAFT)
    return {"owner": owner, "adviser": adviser, "office": office, "stranger": stranger,
            "draft": draft}


def ids(qs):
    return set(qs.values_list("pk", flat=True))


def use_database(settings, name, password):
    settings.AI_RESEARCH_READ_POLICY = "database"
    settings.AI_RESEARCH_DB_USER = name
    settings.AI_RESEARCH_DB_PASSWORD = password
    use_research_alias(name, password)


def test_application_mode_is_visible_to(settings, people):
    settings.AI_RESEARCH_READ_POLICY = "application"
    for key in ("owner", "adviser", "office", "stranger"):
        user = people[key]
        assert ids(reads.research_records(user)) == ids(Record.objects.visible_to(user)), key


def test_database_mode_reads_the_same_population_under_the_restricted_role(settings, grant_db, people):
    with probe_credentials("iris_django_runtime") as (name, password):
        use_database(settings, name, password)
        reads.verify_research_read_configuration()
        for key in ("owner", "adviser", "office", "stranger"):
            user = people[key]
            want = ids(Record.objects.visible_to(user))
            assert ids(reads.research_records(user)) == want, key
        draft = people["draft"]
        assert ids(reads.research_records(people["owner"], scope_record_id=draft.pk)) == {draft.pk}
        assert ids(reads.research_records(people["stranger"], scope_record_id=draft.pk)) == set()


def test_database_mode_reads_nothing_for_an_unauthenticated_or_disabled_reader(settings, grant_db, people):
    from django.contrib.auth.models import AnonymousUser

    with probe_credentials("iris_django_runtime") as (name, password):
        use_database(settings, name, password)
        assert ids(reads.research_records(AnonymousUser())) == set()
        stranger = people["stranger"]
        stranger.is_active = False
        stranger.save(update_fields=["is_active"])
        assert ids(reads.research_records(stranger)) == set()


def test_off_by_default(settings):
    assert reads.mode() == "application"
    settings.AI_RESEARCH_READ_POLICY = "application"
    reads.verify_research_read_configuration()


@pytest.mark.parametrize("value", ["", "both", "Database"])
def test_an_unknown_mode_refuses_to_start(settings, value):
    settings.AI_RESEARCH_READ_POLICY = value
    with pytest.raises(ImproperlyConfigured, match="AI_RESEARCH_READ_POLICY"):
        reads.verify_research_read_configuration()


def test_database_mode_needs_grants_and_credentials(settings):
    settings.AI_RESEARCH_READ_POLICY = "database"
    settings.AI_RESEARCH_GRANTS = False
    settings.AI_RESEARCH_DB_USER = ""
    settings.AI_RESEARCH_DB_PASSWORD = ""
    with pytest.raises(ImproperlyConfigured) as raised:
        reads.verify_research_read_configuration()
    for message in ("AI_RESEARCH_GRANTS", "AI_RESEARCH_DB_USER", "AI_RESEARCH_DB_PASSWORD"):
        assert message in str(raised.value)


def test_database_mode_refuses_owner_and_bypass_credentials(settings, grant_db):
    from django.db import connection

    # The application's own (owner, superuser here) credentials.
    owner = connection.settings_dict
    use_database(settings, owner["USER"], owner["PASSWORD"])
    with pytest.raises(ImproperlyConfigured, match="must not"):
        reads.verify_research_read_configuration()

    with probe_credentials("iris_django_runtime", flags="BYPASSRLS") as (name, password):
        use_database(settings, name, password)
        with pytest.raises(ImproperlyConfigured, match="BYPASSRLS"):
            reads.verify_research_read_configuration()

    with probe_credentials("iris_django_runtime") as (name, password):
        with connection.cursor() as cursor:
            cursor.execute(f'ALTER TABLE public.records_author OWNER TO "{name}"')
        try:
            use_database(settings, name, password)
            with pytest.raises(ImproperlyConfigured, match="owns records_author"):
                reads.verify_research_read_configuration()
        finally:
            with connection.cursor() as cursor:
                cursor.execute("ALTER TABLE public.records_author OWNER TO CURRENT_USER")

    with probe_credentials("iris_ai_runtime") as (name, password):
        use_database(settings, name, password)
        with pytest.raises(ImproperlyConfigured, match="iris_django_runtime"):
            reads.verify_research_read_configuration()


def test_django_startup_runs_the_check(settings):
    from django.apps import apps

    settings.AI_RESEARCH_READ_POLICY = "nonsense"
    # Production startup also requires LlamaParse (IR-843).
    for name, value in {"LLAMAPARSE_API_KEY": "llx-test", "LLAMAPARSE_VERSION": "2026-09-28"}.items():
        setattr(settings, name, value)
    with pytest.raises(ImproperlyConfigured, match="AI_RESEARCH_READ_POLICY"):
        apps.get_app_config("ai").ready()


def test_database_mode_reads_under_a_bound_run_s_own_scope(settings, grant_db, people):
    from .grant_support import owned_run

    owner, draft, stranger = people["owner"], people["draft"], people["stranger"]
    with probe_credentials("iris_django_runtime") as (name, password):
        use_database(settings, name, password)
        assert len(ids(reads.research_records(owner))) > 1
        with reads.bound_run(owned_run(owner, record=draft)):
            assert ids(reads.research_records(owner)) == {draft.pk}
        with reads.bound_run(owned_run(owner, state="succeeded")):
            assert ids(reads.research_records(owner)) == set()
        with reads.bound_run(owned_run(stranger)):
            assert ids(reads.research_records(owner)) == set()
