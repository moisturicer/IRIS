"""The Novelty check: a Proposal's owner sees related published research (IR-312).

ADR-029 §2 and its 2026-09-26 amendment, item 9. A Proposal is compared
against **published** work, and its owner sees the close matches on their own
Proposal as "Related published research", recomputed on every view (§6) --
not a notification, which the amendment replaced.

It needs no consent of any kind: it reads only what the public catalogue
already shows, so it discloses nothing. The test that says so uses published
records with no DPA stamp and no Discoverable setting, because neither is
consulted.

Driven at the HTTP boundary with the deterministic fake embedder, as
`test_similarity.py` is: no vendor account.
"""

from unittest import mock

import pytest
from django.core.exceptions import ImproperlyConfigured
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from apps.ai import similarity
from apps.ai.similarity import verify_novelty_configuration
from apps.records.models import RecordType
from core.enums import PipelineStatus, RecordTypeName
from core.permissions import ROLE_ADVISER, ROLE_RDCO

from . import test_similarity
from .test_similarity import make_record, make_user

# The same fake embedder and active space `test_similarity.py` uses. Bound by
# assignment, not imported by name: a test parameter named after an imported
# fixture reads as a redefinition to pyflakes (F811), which CI gates on.
embedder = test_similarity.embedder
space = test_similarity.space

pytestmark = [pytest.mark.db_required, pytest.mark.django_db]

FLOOD = "Flood prediction with convolutional networks"
FLOOD_ABSTRACT = "rainfall gauge data convolutional network catchment flooding"


def typed(record, type_name):
    record.record_type = RecordType.objects.get_or_create(name=type_name)[0]
    record.save(update_fields=["record_type"])
    return record


def related(record, as_user):
    client = APIClient()
    client.force_authenticate(as_user)
    return client.get(reverse("record-related-research", args=[record.pk]))


@pytest.fixture(autouse=True)
def threshold(settings):
    """Low enough that the fake embedder's near-identical texts clear it."""
    settings.AI_NOVELTY_MIN_SIMILARITY = 0.5


@pytest.fixture
def owner(db):
    return make_user("novelty-owner@cit.edu")


@pytest.fixture
def proposal(owner, embedder, space):
    record = make_record(
        title=FLOOD, abstract=FLOOD_ABSTRACT, embedder=embedder,
        status=PipelineStatus.IN_REVIEW, owner=owner,
    )
    return typed(record, RecordTypeName.PROPOSAL)


def published(title, abstract, embedder, *, status=PipelineStatus.PUBLISHED, owner=None):
    return typed(
        make_record(title=title, abstract=abstract, embedder=embedder, status=status, owner=owner),
        RecordTypeName.THESIS_RESEARCH,
    )


class TestTheOwnerSeesRelatedPublishedResearch:

    def test_a_close_published_record_is_listed_with_its_figure(self, proposal, owner, embedder):
        done = published(FLOOD, FLOOD_ABSTRACT, embedder)

        response = related(proposal, owner)

        assert response.status_code == status.HTTP_200_OK
        rows = response.data["results"]
        assert [row["id"] for row in rows] == [done.pk]
        # The figure is shown, so the proposer can judge a near-duplicate
        # from a loose overlap.
        assert 0.5 <= rows[0]["score"] <= 1.0
        assert response.data["threshold"] == 0.5
        assert response.data["checked"] is True

    def test_matches_need_no_consent(self, proposal, owner, embedder):
        """No DPA stamp and no Discoverable setting on the match: neither is read."""
        done = published(FLOOD, FLOOD_ABSTRACT, embedder)
        assert not done.dpa_accepted

        assert [row["id"] for row in related(proposal, owner).data["results"]] == [done.pk]

    @pytest.mark.parametrize("unpublished", [
        PipelineStatus.DRAFT,
        PipelineStatus.IN_REVIEW,
        PipelineStatus.APPROVED,
        PipelineStatus.COMPLETED,   # accepted but kept unlisted: not public
        PipelineStatus.REJECTED,
    ])
    def test_nothing_unpublished_is_ever_surfaced(self, proposal, owner, embedder, unpublished):
        # Owned by the proposer, so visibility alone would admit it: only
        # "published" keeps it out.
        published(FLOOD, FLOOD_ABSTRACT, embedder, status=unpublished, owner=owner)

        assert related(proposal, owner).data["results"] == []

    def test_a_published_proposal_is_not_completed_work(self, proposal, owner, embedder):
        """Published records of any type count; another Proposal is matching (IR-310), not novelty."""
        other = published(FLOOD, FLOOD_ABSTRACT, embedder)
        typed(other, RecordTypeName.PROPOSAL)

        assert related(proposal, owner).data["results"] == []

    def test_no_close_match_is_an_empty_list_not_a_weak_one(
        self, proposal, owner, embedder, settings,
    ):
        published(
            "Tilapia pond stocking", "brackish water fingerling sampling aquaculture", embedder,
        )
        settings.AI_NOVELTY_MIN_SIMILARITY = 0.99

        response = related(proposal, owner)
        assert response.data["results"] == []
        # Compared, and nothing was close -- not the same as never compared.
        assert response.data["checked"] is True

    def test_the_proposal_never_matches_itself(self, owner, embedder, space):
        own = typed(
            make_record(title=FLOOD, abstract=FLOOD_ABSTRACT, embedder=embedder,
                        status=PipelineStatus.PUBLISHED, owner=owner),
            RecordTypeName.PROPOSAL,
        )

        assert related(own, owner).data["results"] == []

    def test_a_proposal_with_no_vector_yet_says_it_was_not_checked(self, owner, embedder, space):
        published(FLOOD, FLOOD_ABSTRACT, embedder)
        fresh = typed(
            make_record(title=FLOOD, abstract=FLOOD_ABSTRACT, embedder=embedder,
                        status=PipelineStatus.IN_REVIEW, owner=owner, embedded=False),
            RecordTypeName.PROPOSAL,
        )

        response = related(fresh, owner)

        assert response.status_code == status.HTTP_200_OK
        assert response.data["results"] == []
        # Every Proposal is in this state until IR-250, and "nothing close"
        # would be a claim the check never made.
        assert response.data["checked"] is False

    def test_the_query_runs_at_the_configured_scan_depth(self, proposal, owner, embedder):
        """IR-440: unwidened, HNSW hands the filter 40 candidates, so drafts,
        Proposals and other-model vectors near this one could crowd out every
        published match without a sign."""
        published(FLOOD, FLOOD_ABSTRACT, embedder)
        with mock.patch.object(
            similarity, "scan_depth", wraps=similarity.scan_depth,
        ) as depth:
            related(proposal, owner)

        depth.assert_called_once_with()


class TestOnlyAProposalIsTheSubject:

    @pytest.mark.parametrize("type_name", [RecordTypeName.THESIS_RESEARCH, RecordTypeName.PROJECT])
    def test_other_record_types_trigger_nothing(self, owner, embedder, space, type_name):
        published(FLOOD, FLOOD_ABSTRACT, embedder)
        subject = typed(
            make_record(title=FLOOD, abstract=FLOOD_ABSTRACT, embedder=embedder,
                        status=PipelineStatus.IN_REVIEW, owner=owner),
            type_name,
        )

        response = related(subject, owner)
        assert response.data["results"] == []
        assert response.data["checked"] is False


class TestOnlyTheOwnerSeesIt:

    @pytest.mark.parametrize("role", [None, ROLE_ADVISER, ROLE_RDCO])
    def test_anyone_but_an_owner_gets_404(self, proposal, embedder, role):
        published(FLOOD, FLOOD_ABSTRACT, embedder)
        viewer = make_user(f"novelty-viewer-{role}@cit.edu", role)
        if role == ROLE_ADVISER:
            # The Proposal's own Adviser may read it; it is still not theirs.
            proposal.adviser = viewer
            proposal.save(update_fields=["adviser"])

        assert related(proposal, viewer).status_code == status.HTTP_404_NOT_FOUND


class TestTheThresholdIsChecked:
    """A threshold outside (0, 1] silently disables or floods the list, so
    Django refuses to start (CLAUDE.md: fail rather than degrade silently)."""

    @pytest.mark.parametrize("value", [70, 1.5, 0, -0.2])
    def test_an_impossible_threshold_is_refused(self, settings, value):
        settings.AI_NOVELTY_MIN_SIMILARITY = value

        with pytest.raises(ImproperlyConfigured, match="AI_NOVELTY_MIN_SIMILARITY"):
            verify_novelty_configuration()

    @pytest.mark.parametrize("value", [0.7, 1.0, 0.01])
    def test_a_similarity_is_accepted(self, settings, value):
        settings.AI_NOVELTY_MIN_SIMILARITY = value

        verify_novelty_configuration()
