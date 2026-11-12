"""
Account deletion (ADR-051 §8-§12, IR-785).

A person requests deletion and may cancel it. A System Admin confirms or
rejects it, never their own, and RDCO has no access. Confirmation is refused
while somebody is waiting on the person. On confirmation, in one transaction,
the person's details and private data go, the row is kept, and nobody can sign
in as them.
"""

from unittest import mock

from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase
from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken, OutstandingToken
from rest_framework_simplejwt.tokens import RefreshToken

from apps.accounts.deletion import registry
from apps.accounts.deletion.service import former_email
from apps.accounts.models import (
    AccountDeletionRequest, AdviserProfile, Role, RoleRequest, StudentProfile, User, UserSession,
)
from apps.accounts.test_system_admin import make
from apps.ai.models import Conversation
from apps.audit.models import AuditEvent
from apps.library.models import ReadingNote, SavedRecord
from apps.notifications.models import Notification, NotificationType
from apps.records.models import DownloadRequest, Record, RecordOwner, RecordType
from apps.reviews.models import RecordAssignment, Review, ReviewerSeat
from core.enums import PipelineStatus, RequestStatus, RoleName

PASSWORD = "Kalamansi-Tide-42"
SEND = "apps.accounts.deletion.service.send_email_async"


class EveryUserRelationIsDeclared(APITestCase):
    """A new model pointing at `User` must say what deletion does with it (IR-785)."""

    def test_the_registry_names_every_relation_and_nothing_else(self):
        found = {registry.label(model, name) for model, name in registry.user_relations()}
        self.assertEqual(sorted(found - set(registry.RELATIONS)), [],
                         "declare these in apps/accounts/deletion/registry.py")
        self.assertEqual(sorted(set(registry.RELATIONS) - found), [],
                         "these no longer point at User: remove them from the registry")


class DeletionBase(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.sysadmin = make("del-admin@cit.edu", RoleName.SYSTEM_ADMIN)
        cls.other_sysadmin = make("del-admin2@cit.edu", RoleName.SYSTEM_ADMIN)
        cls.rdco = make("del-rdco@cit.edu", RoleName.RDCO)
        cls.itso = make("del-itso@cit.edu", RoleName.ITSO)
        cls.student = make("del-student@cit.edu", RoleName.STUDENT)
        cls.coowner = make("del-coowner@cit.edu", RoleName.STUDENT)
        cls.adviser = make("del-adviser@cit.edu", RoleName.ADVISER)
        cls.thesis = RecordType.objects.get_or_create(name="Thesis / Research")[0]

    def as_(self, user):
        self.client.force_authenticate(user)
        return self.client

    def ask(self, user):
        return self.as_(user).post(reverse("user-me-deletion-request"), {}, format="json")

    def confirm(self, actor, request_id):
        with mock.patch(SEND) as send, self.captureOnCommitCallbacks(execute=True):
            response = self.as_(actor).post(
                reverse("account-deletion-request-confirm", args=[request_id]), {}, format="json")
        return response, send

    def reject(self, actor, request_id, reason="Your thesis is still being examined."):
        with mock.patch(SEND) as send, self.captureOnCommitCallbacks(execute=True):
            response = self.as_(actor).post(
                reverse("account-deletion-request-reject", args=[request_id]), {"reason": reason}, format="json")
        return response, send

    def paper(self, title, *, owners, status=PipelineStatus.IN_REVIEW, adviser=None, primary=None):
        record = Record.objects.create(
            title=title, record_type=self.thesis, added_by=owners[0], pipeline_status=status, adviser=adviser,
        )
        for owner in owners:
            RecordOwner.objects.create(record=record, user=owner, is_primary=owner == (primary or owners[0]))
        return record

    def pending_for(self, user):
        return AccountDeletionRequest.objects.get(user=user, status=RequestStatus.PENDING)


class RequestTests(DeletionBase):
    def test_a_person_requests_deletion_and_holds_at_most_one_pending(self):
        first = self.ask(self.student)
        self.assertEqual(first.status_code, status.HTTP_201_CREATED, first.content)
        self.assertEqual(first.json()["request"]["status"], RequestStatus.PENDING)
        self.assertTrue(first.json()["request"]["can_cancel"])

        again = self.ask(self.student)
        self.assertEqual(again.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(AccountDeletionRequest.objects.filter(user=self.student).count(), 1)
        self.assertTrue(AuditEvent.objects.filter(
            event_type=AuditEvent.ACCOUNT_DELETION_REQUESTED, user=self.student).exists())

    def test_the_person_reads_and_cancels_their_own_request(self):
        self.assertIsNone(self.as_(self.student).get(reverse("user-me-deletion-request")).json()["request"])
        self.ask(self.student)

        cancelled = self.as_(self.student).delete(reverse("user-me-deletion-request"))
        self.assertEqual(cancelled.status_code, status.HTTP_200_OK, cancelled.content)
        self.assertEqual(cancelled.json()["request"]["status"], RequestStatus.CANCELLED)
        self.assertTrue(AuditEvent.objects.filter(
            event_type=AuditEvent.ACCOUNT_DELETION_CANCELLED, user=self.student).exists())
        # Nothing pending is left to cancel, and a new request may be made.
        self.assertEqual(self.as_(self.student).delete(reverse("user-me-deletion-request")).status_code,
                         status.HTTP_409_CONFLICT)
        self.assertEqual(self.ask(self.student).status_code, status.HTTP_201_CREATED)

    def test_a_cancelled_request_cannot_then_be_decided(self):
        self.ask(self.student)
        made = self.pending_for(self.student)
        self.as_(self.student).delete(reverse("user-me-deletion-request"))
        response, _ = self.confirm(self.sysadmin, made.pk)
        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)
        self.student.refresh_from_db()
        self.assertIsNone(self.student.deleted_at)


class DecideTests(DeletionBase):
    def test_only_the_system_admin_lists_and_decides(self):
        self.ask(self.student)
        made = self.pending_for(self.student)
        for actor in (self.rdco, self.itso, self.adviser, self.coowner):
            with self.subTest(actor=actor.email):
                self.assertEqual(self.as_(actor).get(reverse("account-deletion-request-list")).status_code,
                                 status.HTTP_403_FORBIDDEN)
                self.assertEqual(self.confirm(actor, made.pk)[0].status_code, status.HTTP_403_FORBIDDEN)
                self.assertEqual(self.reject(actor, made.pk)[0].status_code, status.HTTP_403_FORBIDDEN)

        listed = self.as_(self.sysadmin).get(reverse("account-deletion-request-list"))
        self.assertEqual(listed.status_code, status.HTTP_200_OK)
        row = listed.json()["results"][0]
        self.assertEqual(row["user"]["email"], self.student.email)
        self.assertEqual(row["blockers"], [])
        self.assertEqual(row["capabilities"], {"can_confirm": True, "can_reject": True})

    def test_nobody_decides_their_own_request(self):
        self.ask(self.sysadmin)
        own = self.pending_for(self.sysadmin)
        listed = self.as_(self.sysadmin).get(reverse("account-deletion-request-list")).json()["results"]
        self.assertEqual(listed[0]["capabilities"], {"can_confirm": False, "can_reject": False})
        self.assertEqual(self.confirm(self.sysadmin, own.pk)[0].status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(self.reject(self.sysadmin, own.pk)[0].status_code, status.HTTP_403_FORBIDDEN)
        # Another System Admin may.
        self.assertEqual(self.reject(self.other_sysadmin, own.pk)[0].status_code, status.HTTP_200_OK)

    def test_a_rejection_needs_a_reason_which_the_person_receives(self):
        self.ask(self.student)
        made = self.pending_for(self.student)
        self.assertEqual(self.reject(self.sysadmin, made.pk, reason="  ")[0].status_code,
                         status.HTTP_400_BAD_REQUEST)

        response, send = self.reject(self.sysadmin, made.pk)
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.content)
        made.refresh_from_db()
        self.assertEqual((made.status, made.decided_by), (RequestStatus.DECLINED, self.sysadmin))
        self.assertIn("still being examined",
                      Notification.objects.get(recipient=self.student).message)
        send.assert_called_once()
        self.assertEqual(send.call_args.kwargs["recipient_list"], [self.student.email])
        self.assertIn("still being examined", send.call_args.kwargs["message"])
        self.assertTrue(AuditEvent.objects.filter(
            event_type=AuditEvent.ACCOUNT_DELETION_REJECTED, user=self.sysadmin).exists())
        self.assertEqual(self.as_(self.student).get(reverse("user-me-deletion-request"))
                         .json()["request"]["reason"], "Your thesis is still being examined.")

    def test_a_second_decision_is_refused_as_stale(self):
        self.ask(self.student)
        made = self.pending_for(self.student)
        self.reject(self.sysadmin, made.pk)
        response, _ = self.confirm(self.other_sysadmin, made.pk)
        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)
        self.assertIn("already decided", response.json()["detail"])


class BlockerTests(DeletionBase):
    def test_a_paper_in_review_with_no_other_owner_blocks(self):
        paper = self.paper("Sole paper", owners=[self.student])
        self.ask(self.student)
        made = self.pending_for(self.student)

        row = self.as_(self.sysadmin).get(reverse("account-deletion-request-list")).json()["results"][0]
        self.assertEqual([b["kind"] for b in row["blockers"]], ["sole_owner_in_review"])
        self.assertIn("RDCO must withdraw it or add an owner", row["blockers"][0]["message"])
        self.assertFalse(row["capabilities"]["can_confirm"])

        response, send = self.confirm(self.sysadmin, made.pk)
        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(response.json()["blockers"][0]["record"], paper.pk)
        send.assert_not_called()
        self.student.refresh_from_db()
        self.assertIsNone(self.student.deleted_at)

    def test_the_person_sees_what_blocks_their_own_pending_request(self):
        paper = self.paper("Sole paper", owners=[self.student])
        self.ask(self.student)

        mine = self.as_(self.student).get(reverse("user-me-deletion-request")).json()["request"]
        self.assertEqual([(b["kind"], b["record"]) for b in mine["blockers"]],
                         [("sole_owner_in_review", paper.pk)])
        self.assertIn("RDCO must withdraw it or add an owner", mine["blockers"][0]["message"])

        # A request no longer pending has nothing left to block it.
        cancelled = self.as_(self.student).delete(reverse("user-me-deletion-request")).json()["request"]
        self.assertEqual(cancelled["blockers"], [])

    def test_a_paper_in_review_with_another_owner_does_not_block(self):
        self.paper("Shared paper", owners=[self.student, self.coowner])
        self.ask(self.student)
        self.assertEqual(self.confirm(self.sysadmin, self.pending_for(self.student).pk)[0].status_code,
                         status.HTTP_200_OK)

    def test_an_open_office_review_blocks_until_reassigned(self):
        paper = self.paper("Reviewed paper", owners=[self.student])
        seat = ReviewerSeat.objects.create(
            assignment=RecordAssignment.objects.create(record=paper, party="itso"),
            reviewer=self.itso, source="claimed",
        )
        self.ask(self.itso)
        made = self.pending_for(self.itso)
        response, _ = self.confirm(self.sysadmin, made.pk)
        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)
        self.assertIn("ITSO coordinator must reassign", response.json()["blockers"][0]["message"])

        seat.state = "withdrawn"
        seat.save(update_fields=["state"])
        self.assertEqual(self.confirm(self.sysadmin, made.pk)[0].status_code, status.HTTP_200_OK)

    def test_an_adviser_the_paper_waits_on_blocks(self):
        paper = self.paper("Advised paper", owners=[self.student], adviser=self.adviser)
        RecordAssignment.objects.create(record=paper, party="adviser")
        self.ask(self.adviser)
        response, _ = self.confirm(self.sysadmin, self.pending_for(self.adviser).pk)
        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)
        blockers = response.json()["blockers"]
        self.assertEqual(len(blockers), 1)
        self.assertIn("RDCO must replace the Adviser", blockers[0]["message"])

    def test_a_draft_nobody_else_waits_on_does_not_block_and_is_deleted(self):
        draft = self.paper("My draft", owners=[self.student], status=PipelineStatus.DRAFT)
        shared = self.paper("Our draft", owners=[self.student, self.coowner], status=PipelineStatus.DRAFT)
        self.ask(self.student)
        self.assertEqual(self.confirm(self.sysadmin, self.pending_for(self.student).pk)[0].status_code,
                         status.HTTP_200_OK)
        self.assertFalse(Record.objects.filter(pk=draft.pk).exists())
        self.assertTrue(Record.objects.filter(pk=shared.pk).exists())


class ConfirmTests(DeletionBase):
    def setUp(self):
        self.person = make("del-leaving@cit.edu", RoleName.ADVISER, middle_initial="Q")
        AdviserProfile.objects.create(user=self.person)
        self.published = self.paper("Published work", owners=[self.student], adviser=self.person,
                                    status=PipelineStatus.PUBLISHED)
        self.co_owned = self.paper("Co-owned", owners=[self.person, self.coowner, self.student],
                                   status=PipelineStatus.PUBLISHED)
        Review.objects.create(record=self.published, reviewed_by=self.person, stage="adviser", status="approved")
        SavedRecord.objects.create(owner=self.person, record=self.published)
        Conversation.objects.create(user=self.person, title="Private")
        Notification.objects.create(recipient=self.person, message="Yours",
                                    notif_type=NotificationType.objects.first())
        RoleRequest.objects.create(user=self.person, requested_role=Role.objects.get(name=RoleName.ADVISER))
        DownloadRequest.objects.create(record=self.co_owned, requested_by=self.person)
        self.token = RefreshToken.for_user(self.person)
        self.ask(self.person)
        self.made = self.pending_for(self.person)

    def test_the_person_s_details_and_private_data_go_in_one_act(self):
        email = self.person.email
        response, send = self.confirm(self.sysadmin, self.made.pk)
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.content)

        self.person.refresh_from_db()
        self.assertIsNotNone(self.person.deleted_at)
        self.assertEqual(self.person.get_full_name(), "Former user")
        self.assertEqual(self.person.email, former_email(self.person.pk))
        self.assertFalse(self.person.is_active)
        self.assertIsNone(self.person.role)
        self.assertFalse(self.person.has_usable_password())
        self.assertFalse(AdviserProfile.objects.filter(user=self.person).exists())
        for model, field in ((SavedRecord, "owner"), (Conversation, "user"), (Notification, "recipient")):
            with self.subTest(model=model.__name__):
                self.assertFalse(model.objects.filter(**{field: self.person}).exists())
        self.assertFalse(RoleRequest.objects.filter(user=self.person, status=RequestStatus.PENDING).exists())
        self.assertFalse(DownloadRequest.objects.filter(requested_by=self.person).exists())

        # The outcome email goes to the address they had, before it was removed.
        send.assert_called_once()
        self.assertEqual(send.call_args.kwargs["recipient_list"], [email])
        self.assertTrue(AuditEvent.objects.filter(
            event_type=AuditEvent.ACCOUNT_DELETION_CONFIRMED, metadata__target_user=email).exists())

    def test_which_papers_they_viewed_is_forgotten_and_the_count_kept(self):
        """IR-369: the record of who viewed a paper goes; the paper's views stay."""
        from apps.records.models import RecordView

        self.client.force_authenticate(self.person)
        opened = self.client.post(f"/api/v1/records/{self.published.pk}/increment_access/")
        self.assertEqual(opened.data["access_count"], 1)
        self.client.force_authenticate(None)

        response, _send = self.confirm(self.sysadmin, self.made.pk)
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.content)

        self.assertFalse(RecordView.objects.filter(user=self.person).exists())
        self.published.refresh_from_db()
        self.assertEqual(self.published.access_count, 1)

    def test_the_optional_profile_goes_with_the_person(self):
        from apps.accounts import profile
        from apps.accounts.models import ResearchInterest
        from apps.library.models import SavedFeed

        self.person.bio = "I study mangroves."
        self.person.photo = "profile_photos/gone.jpg"
        self.person.save(update_fields=["bio", "photo"])
        profile.set_interests(self.person, ["Only this person uses it"])
        SavedFeed.objects.create(owner=self.person, name="Water", query={"q": "water"})
        ReadingNote.objects.create(owner=self.person, record=self.published, body="Private thoughts.")

        response, _send = self.confirm(self.sysadmin, self.made.pk)
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.content)

        self.person.refresh_from_db()
        self.assertEqual(self.person.bio, "")
        self.assertFalse(self.person.photo)
        self.assertFalse(self.person.interest_links.exists())
        self.assertFalse(ResearchInterest.objects.filter(name="Only this person uses it").exists())
        self.assertFalse(SavedFeed.objects.filter(owner=self.person).exists())
        self.assertFalse(ReadingNote.objects.filter(owner=self.person).exists())

    def test_the_row_and_the_history_that_points_at_it_survive(self):
        self.confirm(self.sysadmin, self.made.pk)
        self.assertTrue(User.objects.filter(pk=self.person.pk).exists())
        self.assertTrue(RecordOwner.objects.filter(record=self.co_owned, user=self.person).exists())
        self.assertTrue(Review.objects.filter(reviewed_by=self.person).exists())
        self.assertTrue(AuditEvent.objects.filter(user=self.person).exists())

    def test_a_published_paper_keeps_its_adviser_name_as_text(self):
        self.confirm(self.sysadmin, self.made.pk)
        self.published.refresh_from_db()
        self.assertIsNone(self.published.adviser)
        self.assertEqual(self.published.adviser_name, "Test Q User")
        detail = self.as_(self.student).get(reverse("record-detail", args=[self.published.pk]))
        self.assertEqual(detail.json()["adviser_name"], "Test Q User")
        self.assertIsNone(detail.json()["adviser"])

    def test_the_longest_standing_remaining_owner_becomes_contact_person_and_is_told(self):
        self.confirm(self.sysadmin, self.made.pk)
        owners = {o.user_id: o.is_primary for o in RecordOwner.objects.filter(record=self.co_owned)}
        self.assertEqual(owners, {self.person.pk: False, self.coowner.pk: True, self.student.pk: False})
        told = Notification.objects.get(recipient=self.coowner, record=self.co_owned)
        self.assertIn("now the Contact person", told.message)

    def test_they_cannot_sign_in_and_every_session_ends(self):
        UserSession.objects.create(user=self.person, created_at=self.made.created_at,
                                   last_activity_at=self.made.created_at)
        self.confirm(self.sysadmin, self.made.pk)
        self.assertFalse(UserSession.objects.filter(user=self.person, ended_at__isnull=True).exists())
        self.assertTrue(BlacklistedToken.objects.filter(
            token=OutstandingToken.objects.get(jti=self.token["jti"])).exists())
        self.client.force_authenticate(None)
        login = self.client.post(reverse("auth-login"), {"email": "del-leaving@cit.edu", "password": PASSWORD},
                                 format="json")
        self.assertNotEqual(login.status_code, status.HTTP_200_OK)

    def test_they_disappear_from_the_users_page_and_the_adviser_picker(self):
        self.confirm(self.sysadmin, self.made.pk)
        listed = self.as_(self.rdco).get(reverse("user-list"), {"page_size": 200}).json()
        rows = listed["results"] if isinstance(listed, dict) else listed
        self.assertNotIn(self.person.pk, [u["id"] for u in rows])
        self.assertEqual(self.as_(self.rdco).get(reverse("user-detail", args=[self.person.pk])).status_code,
                         status.HTTP_404_NOT_FOUND)
        advisers = self.as_(self.student).get(reverse("user-advisers")).json()
        rows = advisers["results"] if isinstance(advisers, dict) else advisers
        self.assertNotIn(self.person.pk, [u["id"] for u in rows])

    def test_the_freed_email_registers_again_as_a_new_account(self):
        self.confirm(self.sysadmin, self.made.pk)
        fresh = make("del-leaving@cit.edu", RoleName.STUDENT)
        self.assertNotEqual(fresh.pk, self.person.pk)
        self.assertFalse(StudentProfile.objects.filter(user=fresh).exists())
