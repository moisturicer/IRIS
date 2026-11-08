"""
A paper keeps its Contact person's AI answer, and the disclosure check reads it
(ADR-054 decisions 5, 6, 9-13 and 16-17, IR-791).

One class per acceptance criterion. Driven at the HTTP boundary where there is
one (draft creation, `submit/`, the change route), on real Postgres rows. The
suite gives every new user a Yes on the current notice (`conftest.py`);
`answer` sets someone's answer as it stands after they gave it.
"""

from unittest.mock import patch

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from apps.accounts import ai_answer as change
from apps.accounts.models import NoticeAnswer, User
from apps.accounts.tests import make_unanswered, make_user
from apps.ai.extraction import InMemoryExtractor, use_extractor
from apps.ai.policy import Reason, decision_for_record
from apps.audit.models import AuditEvent
from apps.documents.models import DocumentKind, PdfExtraction
from apps.documents.phases import ExtractionPhase
from apps.documents.testing import real_pdf_bytes
from apps.records.ai_answer import store_on_new_draft
from apps.records.models import Record, RecordOwner, RecordType
from apps.records.testing import released_embargo
from core.enums import RoleName

pytestmark = [pytest.mark.db_required, pytest.mark.django_db]

AI_ANSWER = "/api/v1/users/me/ai-answer/"
NOTICE_ANSWER = "/api/v1/auth/notice/answer/"


def answer(user, ai_consent):
    """`user`'s current answer, as the mirror fields hold it after answering."""
    User.objects.filter(pk=user.pk).update(ai_consent=ai_consent)
    user.refresh_from_db()
    return user


def client_for(user):
    client = APIClient()
    client.force_authenticate(user)
    return client


def create_draft(user, **body):
    """A draft created through the API, as Publish creates one."""
    thesis = RecordType.objects.get_or_create(name="Thesis / Research")[0]
    response = client_for(user).post(
        reverse("record-list"), {"title": "A thesis on tilapia feed", "record_type": thesis.pk, **body},
        format="multipart",
    )
    assert response.status_code == status.HTTP_201_CREATED, response.data
    return Record.objects.get(pk=response.data["id"])


def paper(contact, *, ai_consent, title="A paper", released=True):
    """A paper `contact` is Contact person of, storing `ai_consent`."""
    record = Record.objects.create(
        title=title, abstract="An abstract.", is_ip=False, ai_consent=ai_consent,
        record_type=RecordType.objects.get_or_create(name="Thesis / Research")[0],
    )
    RecordOwner.objects.create(record=record, user=contact, is_primary=True)
    if released:
        released_embargo(record.pk)
        record.refresh_from_db()
    return record


@pytest.fixture
def student():
    return make_user("contact@cit.edu", RoleName.STUDENT)


@pytest.fixture
def coowner():
    return make_user("coowner@cit.edu", RoleName.STUDENT)


# --- AC 1: a paper stores its Contact person's answer when its draft is created --

class TestADraftStoresItsContactPersonsAnswer:
    @pytest.mark.parametrize("given", [True, False], ids=["yes", "no"])
    def test_creating_a_draft_copies_the_creators_answer(self, student, given):
        answer(student, given)

        record = create_draft(student)

        assert record.ai_consent is given

    def test_an_unanswered_person_has_nothing_to_copy_and_the_paper_stores_none(self, student):
        """The notice blocks an unanswered person's request, so this can't come
        through the API; the helper still fails closed if it is reached."""
        record = paper(student, ai_consent=None)
        make_unanswered(student)

        assert store_on_new_draft(record, student) is None
        record.refresh_from_db()
        assert record.ai_consent is None

    def test_a_paper_with_no_contact_person_stores_none(self, student):
        record = paper(student, ai_consent=None)

        assert store_on_new_draft(record, None) is None

    def test_a_coowners_answer_does_not_count(self, student, coowner):
        answer(student, True)
        record = create_draft(student)
        RecordOwner.objects.create(record=record, user=answer(coowner, False), is_primary=False)

        record.refresh_from_db()
        assert record.ai_consent is True

    def test_changing_the_answer_later_does_not_change_the_paper(self, student):
        answer(student, True)
        record = create_draft(student)

        response = client_for(student).post(AI_ANSWER, {"ai_consent": False}, format="json")

        assert response.status_code == 200, response.data
        record.refresh_from_db()
        assert record.ai_consent is True

    def test_changing_the_contact_person_does_not_change_the_paper(self, student, coowner):
        answer(student, True)
        record = create_draft(student)
        RecordOwner.objects.filter(record=record).update(is_primary=False)
        RecordOwner.objects.create(record=record, user=answer(coowner, False), is_primary=True)

        record.refresh_from_db()
        assert record.ai_consent is True

    def test_a_paper_with_no_stored_answer_is_refused(self, student):
        record = paper(student, ai_consent=None)

        decision = decision_for_record(record)
        assert decision.allowed is False
        assert Reason.NO_CONSENT in decision.reasons


# --- AC 2: the disclosure check reads the stored answer -------------------------

class TestTheDisclosureCheckReadsTheStoredAnswer:
    @pytest.mark.parametrize(
        ("stored", "allowed"), [(True, True), (False, False), (None, False)],
        ids=["yes", "no", "no-answer"],
    )
    def test_on_real_rows(self, student, stored, allowed):
        record = paper(student, ai_consent=stored)

        assert decision_for_record(record).allowed is allowed

    def test_the_old_per_paper_stamp_no_longer_counts(self, student):
        from django.utils import timezone

        record = paper(student, ai_consent=None)
        Record.objects.filter(pk=record.pk).update(dpa_accepted_at=timezone.now(), dpa_accepted_by=student)
        record.refresh_from_db()

        assert record.dpa_accepted is True
        assert decision_for_record(record).allowed is False

    def test_the_persons_current_answer_is_not_what_is_read(self, student):
        record = paper(answer(student, True), ai_consent=False)

        assert decision_for_record(record).allowed is False


# --- AC 3: submit asks no consent and stamps none ---------------------------------

class TestSubmitAsksNoConsent:
    def test_submit_without_dpa_accepted_succeeds_and_stamps_nothing(self, student):
        adviser = make_user("adviser@cit.edu", RoleName.ADVISER)
        record = create_draft(student)
        Record.objects.filter(pk=record.pk).update(adviser=adviser)

        with patch("apps.ai.tasks.send_to_ai_on_commit") as sent:
            response = client_for(student).post(reverse("record-submit", args=[record.pk]), {}, format="json")

        assert response.status_code == status.HTTP_200_OK, response.data
        record.refresh_from_db()
        assert record.dpa_accepted_at is None
        assert record.dpa_accepted_by is None
        sent.assert_not_called()


# --- AC 4: a person changes their own answer --------------------------------------

class TestChangingTheAnswer:
    def test_it_needs_a_signed_in_person(self):
        response = APIClient().post(AI_ANSWER, {"ai_consent": False}, format="json")

        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_it_changes_only_the_callers_own_answer(self, student, coowner):
        """There is no id to name: a body naming another account changes nothing of theirs."""
        answer(coowner, True)

        response = client_for(student).post(
            AI_ANSWER, {"ai_consent": False, "user": coowner.pk, "id": coowner.pk}, format="json",
        )

        assert response.status_code == 200, response.data
        student.refresh_from_db()
        coowner.refresh_from_db()
        assert student.ai_consent is False
        assert coowner.ai_consent is True

    def test_the_answer_is_required(self, student):
        response = client_for(student).post(AI_ANSWER, {}, format="json")

        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_yes_to_no_reaches_forward_only(self, student):
        earlier = paper(answer(student, True), ai_consent=True)

        response = client_for(student).post(AI_ANSWER, {"ai_consent": False}, format="json")

        assert response.status_code == 200, response.data
        assert response.data["changed"] is True
        assert response.data["papers_updated"] == 0
        earlier.refresh_from_db()
        assert earlier.ai_consent is True
        student.refresh_from_db()
        assert create_draft(student).ai_consent is False
        assert NoticeAnswer.objects.filter(user=student, ai_consent=False).exists()

    def test_no_to_yes_without_a_papers_choice_is_refused_and_writes_nothing(self, student):
        held = paper(answer(student, False), ai_consent=False)
        answers_before = NoticeAnswer.objects.filter(user=student).count()

        response = client_for(student).post(AI_ANSWER, {"ai_consent": True}, format="json")

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert response.data["code"] == change.PAPERS_CHOICE_REQUIRED_CODE
        student.refresh_from_db()
        held.refresh_from_db()
        assert student.ai_consent is False
        assert held.ai_consent is False
        assert NoticeAnswer.objects.filter(user=student).count() == answers_before
        assert not AuditEvent.objects.filter(event_type=AuditEvent.AI_ANSWER_CHANGED).exists()

    def test_no_to_yes_from_now_leaves_earlier_papers_with_their_no(self, student):
        held = paper(answer(student, False), ai_consent=False)

        with patch("apps.ai.tasks.send_to_ai_on_commit") as sent:
            response = client_for(student).post(
                AI_ANSWER, {"ai_consent": True, "papers": "from_now"}, format="json",
            )

        assert response.status_code == 200, response.data
        assert response.data["papers_updated"] == 0
        held.refresh_from_db()
        assert held.ai_consent is False
        sent.assert_not_called()
        student.refresh_from_db()
        assert create_draft(student).ai_consent is True

    def test_no_to_yes_for_all_reaches_only_contact_papers_holding_a_no(self, student, coowner):
        answer(student, False)
        mine_no = paper(student, ai_consent=False, title="Mine, No")
        mine_none = paper(student, ai_consent=None, title="Mine, no answer")
        coowned = paper(answer(coowner, False), ai_consent=False, title="A co-owner's")
        RecordOwner.objects.create(record=coowned, user=student, is_primary=False)

        with patch("apps.ai.tasks.send_to_ai_on_commit") as sent:
            response = client_for(student).post(
                AI_ANSWER, {"ai_consent": True, "papers": "all"}, format="json",
            )

        assert response.status_code == 200, response.data
        assert response.data["papers_updated"] == 1
        for record in (mine_no, mine_none, coowned):
            record.refresh_from_db()
        assert mine_no.ai_consent is True
        assert mine_none.ai_consent is None
        assert coowned.ai_consent is False
        sent.assert_called_once_with(mine_no.pk)

    def test_all_still_leaves_the_embargo_and_ip_checks_in_place(self, student):
        answer(student, False)
        embargoed = paper(student, ai_consent=False, title="Embargoed", released=False)
        marked = paper(student, ai_consent=False, title="IP")
        Record.objects.filter(pk=marked.pk).update(is_ip=True)

        response = client_for(student).post(AI_ANSWER, {"ai_consent": True, "papers": "all"}, format="json")

        assert response.status_code == 200, response.data
        for record in (embargoed, marked):
            record.refresh_from_db()
            assert record.ai_consent is True
            assert decision_for_record(record).allowed is False

    def test_saying_the_same_thing_again_changes_and_audits_nothing(self, student):
        answer(student, True)

        response = client_for(student).post(AI_ANSWER, {"ai_consent": True}, format="json")

        assert response.status_code == 200, response.data
        assert response.data["changed"] is False
        assert not AuditEvent.objects.filter(event_type=AuditEvent.AI_ANSWER_CHANGED).exists()

    def test_it_is_blocked_until_the_current_notice_is_answered(self, student):
        make_unanswered(student)

        response = client_for(student).post(AI_ANSWER, {"ai_consent": True, "papers": "all"}, format="json")

        assert response.status_code == status.HTTP_403_FORBIDDEN


# --- AC 4 at the notice: the same two choices -------------------------------------

class TestANoticeAnswerOffersTheSameChoice:
    def _notice(self):
        from apps.accounts.notice import current_notice_number

        return current_notice_number()

    def test_no_to_yes_at_the_notice_needs_a_papers_choice(self, student):
        answer(student, False)

        response = client_for(student).post(
            NOTICE_ANSWER, {"notice_version": self._notice(), "agree_dpa": True, "ai_consent": True},
            format="json",
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert response.data["code"] == change.PAPERS_CHOICE_REQUIRED_CODE

    def test_all_at_the_notice_reaches_the_papers_and_is_audited(self, student):
        held = paper(answer(student, False), ai_consent=False)

        with patch("apps.ai.tasks.send_to_ai_on_commit") as sent:
            response = client_for(student).post(
                NOTICE_ANSWER,
                {"notice_version": self._notice(), "agree_dpa": True, "ai_consent": True, "papers": "all"},
                format="json",
            )

        assert response.status_code == 201, response.data
        assert response.data["papers_updated"] == 1
        held.refresh_from_db()
        assert held.ai_consent is True
        sent.assert_called_once_with(held.pk)
        assert AuditEvent.objects.filter(event_type=AuditEvent.AI_ANSWER_CHANGED).count() == 1


# --- AC 5: everything runs at upload when the check allows it ---------------------

class TestUploadRunsWhenTheCheckAllows:
    @pytest.mark.parametrize(("given", "held"), [(True, False), (False, True)], ids=["yes", "no"])
    def test_a_released_paper_is_read_at_upload_only_with_a_yes(self, student, given, held):
        answer(student, given)
        record = create_draft(student)
        released_embargo(record.pk)
        upload = SimpleUploadedFile("thesis.pdf", real_pdf_bytes(), content_type="application/pdf")

        with use_extractor(InMemoryExtractor(None, leaves_campus=True)), \
                patch("apps.documents.tasks.extract_manuscript_text.delay"):
            response = client_for(student).patch(
                reverse("record-detail", args=[record.pk]), {"abstract_file": upload}, format="multipart",
            )

        assert response.status_code == status.HTTP_200_OK, response.data
        extraction = PdfExtraction.objects.get(record=record, kind=DocumentKind.MANUSCRIPT)
        assert (extraction.phase == ExtractionPhase.AWAITING_DISCLOSURE) is held


# --- AC 9: changing an answer is audited ------------------------------------------

class TestAChangeIsAudited:
    def test_the_event_names_the_change_and_the_papers_by_id(self, student):
        held = paper(answer(student, False), ai_consent=False)

        client_for(student).post(AI_ANSWER, {"ai_consent": True, "papers": "all"}, format="json")

        event = AuditEvent.objects.get(event_type=AuditEvent.AI_ANSWER_CHANGED)
        assert event.user_id == student.pk
        assert event.metadata["previous_ai_consent"] is False
        assert event.metadata["ai_consent"] is True
        assert event.metadata["papers"] == "all"
        assert event.metadata["papers_updated"] == 1
        assert event.metadata["paper_ids"] == [held.pk]
        assert held.title not in str(event.metadata)
