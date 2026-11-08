"""
Owners choose a paper's Contact person (ADR-051 decision 27, IR-801).

One class per acceptance criterion, driven at `POST /records/<id>/contact-person/`
on real Postgres rows, except where the criterion is about the service itself
(`set_primary_owner` can't add a stranger) or about what happens later (the
next review email).
"""

from types import SimpleNamespace
from unittest.mock import patch

import pytest
from django.db import connection
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from apps.accounts.tests import make_user
from apps.audit.models import AuditEvent
from apps.notifications.models import Notification
from apps.notifications.services import notify_revision_requested
from apps.records.contact_person import ACCOUNT_CLOSED, ALREADY_CONTACT, NOT_AN_OWNER
from apps.records.models import Record, RecordOwner, RecordType
from apps.records.services import NotAnOwner, set_primary_owner
from core.enums import PipelineStatus, RecordTypeName, RoleName

pytestmark = [pytest.mark.db_required, pytest.mark.django_db]


def url(record):
    return reverse("record-contact-person", args=[record.pk])


def post(user, record, body):
    client = APIClient()
    client.force_authenticate(user)
    return client.post(url(record), body, format="json")


def contacts(record):
    return list(RecordOwner.objects.filter(record=record, is_primary=True).values_list("user_id", flat=True))


@pytest.fixture
def ana():
    return make_user("ana@cit.edu", RoleName.STUDENT)


@pytest.fixture
def ben():
    return make_user("ben@cit.edu", RoleName.STUDENT)


@pytest.fixture
def carla():
    return make_user("carla@cit.edu", RoleName.STUDENT)


@pytest.fixture
def adviser():
    return make_user("adviser@cit.edu", RoleName.ADVISER)


def make_paper(owners, *, status=PipelineStatus.DRAFT, type_name=RecordTypeName.THESIS_RESEARCH,
               adviser=None, ai_consent=True):
    """A paper owned by `owners`, the first of them its Contact person."""
    record = Record.objects.create(
        title="Tilapia feed trials", abstract="An abstract.", is_ip=False,
        pipeline_status=status, adviser=adviser, ai_consent=ai_consent,
        record_type=RecordType.objects.get_or_create(name=type_name)[0],
    )
    for index, owner in enumerate(owners):
        RecordOwner.objects.create(record=record, user=owner, is_primary=index == 0)
    return record


# --- AC 1: any owner, every record type, any time until deletion ----------------

class TestAnyOwnerNamesAnotherOwner:
    @pytest.mark.parametrize("type_name", list(RecordTypeName))
    @pytest.mark.parametrize("state", [
        PipelineStatus.DRAFT, PipelineStatus.IN_REVIEW, PipelineStatus.PUBLISHED,
    ])
    def test_the_contact_person_hands_it_to_a_co_owner(self, ana, ben, type_name, state):
        record = make_paper([ana, ben], status=state, type_name=type_name)

        response = post(ana, record, {"owner": ben.pk})

        assert response.status_code == status.HTTP_200_OK, response.data
        assert contacts(record) == [ben.pk]
        assert response.data["owners"][0] == {"id": ben.pk, "name": "Test User", "is_primary": True}

    def test_an_owner_who_is_not_the_contact_person_can_change_it_too(self, ana, ben, carla):
        record = make_paper([ana, ben, carla])

        response = post(carla, record, {"owner": ben.pk})

        assert response.status_code == status.HTTP_200_OK, response.data
        assert contacts(record) == [ben.pk]

    def test_an_owner_can_name_themselves(self, ana, ben):
        record = make_paper([ana, ben])

        response = post(ben, record, {"owner": str(ben.pk)})

        assert response.status_code == status.HTTP_200_OK, response.data
        assert contacts(record) == [ben.pk]

    def test_a_deleted_paper_is_not_found(self, ana, ben):
        record = make_paper([ana, ben])
        Record.objects.filter(pk=record.pk).update(is_deleted=True)

        response = post(ana, record, {"owner": ben.pk})

        assert response.status_code == status.HTTP_404_NOT_FOUND
        assert contacts(Record.objects.with_deleted().get(pk=record.pk)) == [ana.pk]

    def test_it_leaves_the_papers_stored_ai_answer_alone(self, ana, ben):
        """IR-791: the paper keeps the answer its Contact person had when the draft
        was created; a later change of Contact person doesn't touch it."""
        record = make_paper([ana, ben], ai_consent=False)

        post(ana, record, {"owner": ben.pk})

        record.refresh_from_db()
        assert record.ai_consent is False


# --- AC 2: refusals -------------------------------------------------------------

class TestRefusals:
    def test_someone_who_cannot_see_the_paper_gets_not_found(self, ana, ben, carla):
        record = make_paper([ana, ben])

        response = post(carla, record, {"owner": carla.pk})

        assert response.status_code == status.HTTP_404_NOT_FOUND
        assert contacts(record) == [ana.pk]

    def test_a_reader_of_a_published_paper_who_does_not_own_it_is_refused(self, ana, ben, carla):
        record = make_paper([ana, ben], status=PipelineStatus.PUBLISHED)

        response = post(carla, record, {"owner": ben.pk})

        assert response.status_code == status.HTTP_403_FORBIDDEN
        assert contacts(record) == [ana.pk]

    @pytest.mark.parametrize("body", [
        {}, {"owner": None}, {"owner": "x"}, {"owner": True}, {"owner": [1]},
    ], ids=["missing", "null", "text", "bool", "list"])
    def test_a_malformed_target_is_refused(self, ana, ben, body):
        record = make_paper([ana, ben])

        response = post(ana, record, body)

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert response.data["owner"] == [NOT_AN_OWNER]
        assert contacts(record) == [ana.pk]

    def test_a_target_who_does_not_own_the_paper_is_refused_and_not_added(self, ana, ben, carla):
        record = make_paper([ana, ben])

        response = post(ana, record, {"owner": carla.pk})

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert response.data["owner"] == [NOT_AN_OWNER]
        assert not RecordOwner.objects.filter(record=record, user=carla).exists()
        assert contacts(record) == [ana.pk]

    def test_the_current_contact_person_is_refused_and_nothing_is_written(self, ana, ben):
        record = make_paper([ana, ben])

        response = post(ben, record, {"owner": ana.pk})

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert response.data["owner"] == [ALREADY_CONTACT]
        assert not AuditEvent.objects.filter(event_type=AuditEvent.CONTACT_PERSON_CHANGED).exists()

    def test_an_owner_whose_account_is_closed_is_refused(self, ana, ben):
        """A deleted account keeps its ownership row (ADR-051 decision 28), and
        review emails to it would reach nobody."""
        record = make_paper([ana, ben])
        ben.is_active = False
        ben.save(update_fields=["is_active"])

        response = post(ana, record, {"owner": ben.pk})

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert response.data["owner"] == [ACCOUNT_CLOSED]
        assert contacts(record) == [ana.pk]


class TestSetPrimaryOwnerNeverAddsAStranger:
    def test_a_stranger_raises_and_nothing_changes(self, ana, ben, carla):
        record = make_paper([ana, ben])

        with pytest.raises(NotAnOwner):
            set_primary_owner(record, carla)

        assert not RecordOwner.objects.filter(record=record, user=carla).exists()
        assert contacts(record) == [ana.pk]

    def test_an_owner_is_promoted_without_a_new_row(self, ana, ben):
        record = make_paper([ana, ben])

        set_primary_owner(record, ben)

        assert RecordOwner.objects.filter(record=record).count() == 2
        assert contacts(record) == [ben.pk]


# --- AC 3: always exactly one ---------------------------------------------------

class TestAlwaysExactlyOne:
    def test_a_paper_with_two_stale_contacts_ends_with_exactly_one(self, ana, ben, carla):
        """Even a paper left with two primary rows by older data is repaired."""
        record = make_paper([ana, ben, carla])
        RecordOwner.objects.filter(record=record, user=ben).update(is_primary=True)

        post(carla, record, {"owner": carla.pk})

        assert contacts(record) == [carla.pk]

    def test_a_failure_after_clearing_the_old_contact_rolls_both_back(self, ana, ben):
        record = make_paper([ana, ben])

        with patch.object(RecordOwner, "save", side_effect=RuntimeError("boom")):
            with pytest.raises(RuntimeError):
                set_primary_owner(record, ben)

        assert contacts(record) == [ana.pk]

    def test_the_owner_rows_are_locked_for_the_change(self, ana, ben):
        record = make_paper([ana, ben])
        from django.test.utils import CaptureQueriesContext

        with CaptureQueriesContext(connection) as queries:
            set_primary_owner(record, ben)

        assert any(
            "FOR UPDATE" in q["sql"] and "records_recordowner" in q["sql"] for q in queries.captured_queries
        )


# --- AC 4: both told in-app, one audit event --------------------------------------

class TestBothToldAndAudited:
    def test_the_old_and_new_contact_person_are_told_in_app(self, ana, ben, carla, django_capture_on_commit_callbacks):
        record = make_paper([ana, ben, carla])

        with django_capture_on_commit_callbacks(execute=True):
            post(carla, record, {"owner": ben.pk})

        told = Notification.objects.filter(record=record)
        assert {n.recipient_id for n in told} == {ana.pk, ben.pk}
        assert "made you the Contact person" in told.get(recipient=ben).message
        assert "not to you" in told.get(recipient=ana).message
        assert {n.notif_type.name for n in told} == {"Contact Person Changed"}

    def test_one_audit_event_names_the_paper_both_people_and_the_actor(self, ana, ben, carla):
        record = make_paper([ana, ben, carla])

        post(carla, record, {"owner": ben.pk})

        [event] = AuditEvent.objects.filter(event_type=AuditEvent.CONTACT_PERSON_CHANGED)
        assert event.record_id == record.pk
        assert event.user_id == carla.pk
        assert event.metadata == {"previous_contact": ana.pk, "contact": ben.pk}

    def test_a_refusal_writes_no_event_and_tells_no_one(self, ana, ben, carla, django_capture_on_commit_callbacks):
        record = make_paper([ana, ben])

        with django_capture_on_commit_callbacks(execute=True):
            post(ana, record, {"owner": carla.pk})

        assert not AuditEvent.objects.filter(event_type=AuditEvent.CONTACT_PERSON_CHANGED).exists()
        assert not Notification.objects.filter(record=record).exists()


# --- AC 5: RDCO, the Adviser and the offices have no say --------------------------

class TestNoOfficeHasASay:
    @pytest.mark.parametrize("role", [
        RoleName.RDCO, RoleName.ITSO, RoleName.IERC, RoleName.KTTO, RoleName.SYSTEM_ADMIN,
    ])
    def test_an_office_or_the_system_admin_is_refused(self, ana, ben, role):
        record = make_paper([ana, ben], status=PipelineStatus.PUBLISHED)
        staff = make_user(f"{role.lower().replace(' ', '')}@cit.edu", role)

        response = post(staff, record, {"owner": ben.pk})

        assert response.status_code in (status.HTTP_403_FORBIDDEN, status.HTTP_404_NOT_FOUND)
        assert contacts(record) == [ana.pk]

    def test_rdco_is_refused_on_a_paper_it_can_see(self, ana, ben):
        record = make_paper([ana, ben], status=PipelineStatus.IN_REVIEW)
        rdco = make_user("rdco@cit.edu", RoleName.RDCO)

        response = post(rdco, record, {"owner": ben.pk})

        assert response.status_code == status.HTTP_403_FORBIDDEN
        assert contacts(record) == [ana.pk]

    def test_the_papers_adviser_is_refused(self, ana, ben, adviser):
        record = make_paper([ana, ben], status=PipelineStatus.IN_REVIEW, adviser=adviser)

        response = post(adviser, record, {"owner": ben.pk})

        assert response.status_code == status.HTTP_403_FORBIDDEN
        assert contacts(record) == [ana.pk]


# --- AC 6: review emails go to the new Contact person ----------------------------

class TestReviewEmailsFollowTheChange:
    def test_the_next_revision_request_emails_the_new_contact_person(self, ana, ben, adviser):
        record = make_paper([ana, ben], status=PipelineStatus.IN_REVIEW, adviser=adviser)
        assert post(ana, record, {"owner": ben.pk}).status_code == status.HTTP_200_OK
        request = SimpleNamespace(record=record, requested_by=adviser, reason="Fix chapter 2.")

        with patch("apps.notifications.services.send_email_async") as send:
            notify_revision_requested(request, party_label="The Adviser")

        [call] = send.call_args_list
        assert call.kwargs["recipient_list"] == [ben.email]
        # Every owner still gets the in-app notice.
        assert set(
            Notification.objects.filter(record=record, notif_type__name="Revision Requested")
            .values_list("recipient_id", flat=True)
        ) == {ana.pk, ben.pk}
