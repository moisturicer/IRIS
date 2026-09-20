"""The development-only disclosure bypass (IR-317, ADR-015 §A development bypass).

The switch is not what makes this acceptable — these tests are. ADR-015 permits
the bypass under four conditions, and three of them are assertions rather than
prose: it cannot run in production, it is loud while it runs, and it is off
unless somebody turned it on. The fourth (it points only at content already
cleared to leave) is a judgement about which corpus is loaded and cannot be
asserted here.

**These tests are also the removal trigger.** IR-250 deletes the setting, the
guard, the command and the status flag together; every test in this file fails
if a piece is left behind, which is the point — a bypass that can be half
removed is a bypass that stays.
"""

import logging
import pathlib

import pytest
from django.apps import apps as django_apps
from django.core.exceptions import ImproperlyConfigured
from django.utils import timezone

from apps.ai.policy.bypass import (
    SETTING,
    bypass_configuration_problem,
    bypass_enabled,
    permit_everything,
    verify_bypass_configuration,
)

BASE_SETTINGS = (
    pathlib.Path(__file__).resolve().parents[3] / "config" / "settings" / "base.py"
)


# -- condition 3: off by default ---------------------------------------------


def test_the_bypass_is_declared_with_a_default_of_off():
    """Asserted against the declaration, not against this machine's environment.

    A developer who has turned the bypass on locally — which is the whole
    workflow this ticket enables — would otherwise fail this test for doing
    exactly what it permits. What must stay true is the *shipped* default, so
    that is what is read.
    """
    declaration = "".join(BASE_SETTINGS.read_text(encoding="utf-8").split())
    assert f'"{SETTING}",default=False' in declaration, (
        f"{SETTING} must be declared with default=False in config/settings/base.py"
    )


def test_the_bypass_is_off_when_no_setting_configures_it(settings):
    del settings.AI_DISCLOSURE_BYPASS_FOR_DEVELOPMENT
    assert bypass_enabled() is False


# -- condition 1: it cannot run in production --------------------------------


def test_the_bypass_with_debug_off_is_a_configuration_problem():
    problem = bypass_configuration_problem(enabled=True, debug=False)
    assert problem is not None
    assert SETTING in problem


@pytest.mark.parametrize(
    "enabled,debug",
    [(False, False), (False, True), (True, True)],
    ids=["off in production", "off in development", "on in development"],
)
def test_every_other_combination_is_fine(enabled, debug):
    assert bypass_configuration_problem(enabled=enabled, debug=debug) is None


def test_the_application_refuses_to_start_with_the_bypass_set_and_debug_off(settings):
    settings.DEBUG = False
    settings.AI_DISCLOSURE_BYPASS_FOR_DEVELOPMENT = True
    with pytest.raises(ImproperlyConfigured) as raised:
        verify_bypass_configuration()
    assert SETTING in str(raised.value)


def test_app_startup_is_what_runs_that_check(settings):
    """Not a unit test of the guard — a test that the guard is *wired*.

    A perfect check nothing calls is the failure mode here, so this drives
    `AppConfig.ready()`, which is the real startup path.
    """
    settings.DEBUG = False
    settings.AI_DISCLOSURE_BYPASS_FOR_DEVELOPMENT = True
    with pytest.raises(ImproperlyConfigured):
        django_apps.get_app_config("ai").ready()


# -- condition 2: it is loud while it runs -----------------------------------


#: `apps` sets `propagate: False`, so records never reach the root logger
#: `caplog` attaches to by default — the handler has to go on this logger, or
#: the assertion below passes vacuously.
_BYPASS_LOGGER = "apps.ai.policy.bypass"


@pytest.fixture
def bypass_logs(caplog):
    logger = logging.getLogger(_BYPASS_LOGGER)
    logger.addHandler(caplog.handler)
    caplog.set_level(logging.WARNING, logger=_BYPASS_LOGGER)
    try:
        yield caplog
    finally:
        logger.removeHandler(caplog.handler)


def test_permitting_everything_logs_a_warning(bypass_logs):
    class _Record:
        pk = 7
        title = "A thesis"

    decision = permit_everything(_Record())

    assert bool(decision) is True
    assert "bypass" in bypass_logs.text.lower()
    # Which record, not just that something happened: the question a log
    # reader asks later is whether *this* content was sent under the bypass.
    assert "7" in bypass_logs.text


def test_the_query_lane_gets_a_real_bool():
    """The two lanes take differently shaped predicates, and both annotations
    should stay true — `Decision` is truthy, so a single function would work
    while making one of them a lie."""
    from apps.ai.policy.bypass import permits_query

    assert permits_query(object()) is True


def test_installing_the_bypass_never_replaces_a_root_somebody_else_set(settings):
    """Otherwise a developer running the suite with the bypass on would have
    it reinstalled over a test's own root — reopening the gate under a test
    written to assert it closed."""
    from apps.ai.composition import CompositionRoot, use_composition_root
    from apps.ai.policy.bypass import install_bypass_if_enabled

    settings.AI_DISCLOSURE_BYPASS_FOR_DEVELOPMENT = True
    mine = CompositionRoot()
    with use_composition_root(mine) as installed:
        assert install_bypass_if_enabled() is False
        from apps.ai.composition import composition_root

        assert composition_root() is installed


# -- the indexing seam --------------------------------------------------------


@pytest.mark.db_required
@pytest.mark.django_db
class TestIndexingTakesAnInjectedPredicate:
    """`permits` is injectable on both entry points, and defaults to the gate.

    The default matters more than the injection: a parameter added for a dev
    tool that also quietly changed the production default would be the exact
    accident ADR-015 forbids.
    """

    @pytest.fixture(autouse=True)
    def _space(self):
        from apps.ai.models import (
            VECTOR_COLUMN_DIMENSIONS,
            EmbeddingSpace,
            EmbeddingSpaceState,
        )

        EmbeddingSpace.objects.all().delete()
        return EmbeddingSpace.objects.create(
            model_id="voyage-context-4",
            dimensions=VECTOR_COLUMN_DIMENSIONS,
            metric="cosine",
            state=EmbeddingSpaceState.ACTIVE,
        )

    @pytest.fixture
    def record(self):
        from apps.records.models import Record

        return Record.objects.create(
            title="Rainfall prediction in the Mananga catchment",
            abstract="An abstract about rainfall gauges.",
            is_ip=False,
            dpa_accepted_at=timezone.now(),
        )

    @pytest.fixture
    def embedder(self):
        from apps.ai.models import VECTOR_COLUMN_DIMENSIONS
        from apps.ai.providers.fakes import DeterministicEmbeddingProvider

        return DeterministicEmbeddingProvider(dimensions=VECTOR_COLUMN_DIMENSIONS)

    def _with_chunks(self, record, *texts):
        from apps.ai.chunking import Chunk, ChunkingOptions, ChunkSet, chunkset_hash
        from apps.ai.repositories import DjangoChunkRepository

        chunks = tuple(
            Chunk(
                text=text,
                content=text,
                context_path=(),
                sequence=index,
                token_count=len(text.split()),
            )
            for index, text in enumerate(texts)
        )
        return DjangoChunkRepository().save(
            record_id=record.id,
            extraction_hash="extraction-hash",
            chunk_set=ChunkSet(
                chunks=chunks,
                strategy_id="fixed-window",
                options=ChunkingOptions(),
                content_hash=chunkset_hash(chunks),
            ),
        )

    def test_the_summary_path_refuses_by_default(self, record, embedder):
        from apps.ai.indexing import embed_record_summary

        outcome = embed_record_summary(record.id, provider=embedder)

        assert outcome.refused is True
        assert outcome.embedded == 0

    def test_the_summary_path_embeds_with_the_bypass_injected(self, record, embedder):
        from apps.ai.indexing import embed_record_summary

        outcome = embed_record_summary(
            record.id, provider=embedder, permits=permit_everything
        )

        assert outcome.refused is False
        assert outcome.embedded == 1

    def test_the_chunk_path_refuses_by_default(self, record, embedder):
        from apps.ai.indexing import embed_active_chunk_set

        self._with_chunks(record, "a passage about rainfall gauges")
        outcome = embed_active_chunk_set(record.id, provider=embedder)

        assert outcome.refused is True
        assert outcome.embedded == 0

    def test_the_chunk_path_embeds_with_the_bypass_injected(self, record, embedder):
        from apps.ai.indexing import embed_active_chunk_set

        self._with_chunks(record, "a passage about rainfall gauges")
        outcome = embed_active_chunk_set(
            record.id, provider=embedder, permits=permit_everything
        )

        assert outcome.refused is False
        assert outcome.embedded == 1


# -- the status endpoint ------------------------------------------------------


@pytest.mark.db_required
@pytest.mark.django_db
class TestStatusReportsTheBypass:
    """Condition 2's other half: the interface can say so, and a demo
    screenshot labels itself."""

    @pytest.fixture
    def client(self):
        from django.contrib.auth import get_user_model
        from rest_framework.test import APIClient

        user = get_user_model().objects.create_user(
            email="asker@cit.edu", password="x", is_verified=True
        )
        api = APIClient()
        api.force_authenticate(user)
        return api

    def _status(self, client):
        from django.urls import reverse

        return client.get(reverse("ai-status")).data

    def test_it_reports_off_by_default(self, client, settings):
        settings.AI_DISCLOSURE_BYPASS_FOR_DEVELOPMENT = False
        assert self._status(client)["disclosure_bypass"] is False

    def test_it_reports_on_when_the_bypass_is_set(self, client, settings):
        settings.AI_DISCLOSURE_BYPASS_FOR_DEVELOPMENT = True
        assert self._status(client)["disclosure_bypass"] is True


# -- the dev command ----------------------------------------------------------


@pytest.mark.db_required
@pytest.mark.django_db
class TestTheDevCommandRefusesOutsideDevelopment:
    def test_it_refuses_with_debug_off(self, settings):
        from django.core.management import CommandError, call_command

        settings.DEBUG = False
        with pytest.raises(CommandError) as raised:
            call_command("index_with_disclosure_bypass", "--dry-run")
        assert "DEBUG" in str(raised.value)

    def test_force_is_how_somebody_chooses_to_anyway(self, settings):
        from django.core.management import call_command

        settings.DEBUG = False
        # Reaches the plan and stops there: --dry-run sends nothing, so this
        # asserts the guard let it past without spending anything.
        call_command("index_with_disclosure_bypass", "--dry-run", "--force")
