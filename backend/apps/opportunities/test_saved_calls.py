"""
IR-649: a reader's saved Calls are stored in their account (ADR-050
decision 13; owner's decisions of 2026-11-16 on the card).

Every case goes through the HTTP API, the seam IR-766's screens use.
"""
from datetime import datetime, timezone as dt_timezone

from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from core.enums import CallStatus

from apps.audit.models import AuditEvent

from . import review
from .models import Opportunity, SavedCall
from .tasks import remove_lapsed_requests
from .test_call_states import frozen_at, nov
from .test_lapsed_requests import JUST_AFTER_MIDNIGHT_16TH_MANILA
from .tests import make_opportunity, make_user

#: 09:00 on 2026-11-20 in Manila: an event that ended on the 12th is Over.
NINE_AM_20TH_MANILA = datetime(2026, 11, 20, 1, 0, tzinfo=dt_timezone.utc)


class SavedCallsTestCase(APITestCase):
    def setUp(self):
        self.reader = make_user("reader@cit.edu", "Student")
        self.other = make_user("other.reader@cit.edu", "Student")
        self.adviser = make_user("adviser@cit.edu", "Adviser")
        self.rdco = make_user("rdco@cit.edu", "RDCO")

    def as_user(self, user):
        self.client.force_authenticate(user)
        return self.client

    def save_as(self, user, call):
        return self.as_user(user).put(reverse("opportunity-save", args=[call.pk]))

    def unsave_as(self, user, call):
        return self.as_user(user).delete(reverse("opportunity-save", args=[call.pk]))

    def saved(self, user):
        response = self.as_user(user).get(reverse("opportunity-saved"))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        return response.data["results"]


class SaveTests(SavedCallsTestCase):
    def test_a_saved_call_is_listed_in_full(self):
        call = make_opportunity(title="ICACSIS")
        response = self.save_as(self.reader, call)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        [entry] = self.saved(self.reader)
        self.assertEqual(entry["call_id"], call.pk)
        self.assertTrue(entry["available"])
        self.assertIn("saved_at", entry)
        self.assertEqual(entry["call"]["title"], "ICACSIS")
        self.assertEqual(entry["call"]["papers_label"], "Accepting papers")

    def test_saving_twice_is_one_save(self):
        call = make_opportunity()
        self.assertEqual(self.save_as(self.reader, call).status_code, status.HTTP_201_CREATED)
        self.assertEqual(self.save_as(self.reader, call).status_code, status.HTTP_200_OK)
        self.assertEqual(len(self.saved(self.reader)), 1)

    def test_unsaving_removes_it_and_unsaving_again_is_still_204(self):
        call = make_opportunity()
        self.save_as(self.reader, call)
        self.assertEqual(self.unsave_as(self.reader, call).status_code, status.HTTP_204_NO_CONTENT)
        self.assertEqual(self.saved(self.reader), [])
        self.assertEqual(self.unsave_as(self.reader, call).status_code, status.HTTP_204_NO_CONTENT)

    def test_newest_save_first(self):
        first, second = make_opportunity(title="First"), make_opportunity(title="Second")
        self.save_as(self.reader, first)
        self.save_as(self.reader, second)
        self.assertEqual([e["call"]["title"] for e in self.saved(self.reader)], ["Second", "First"])


class OwnerTests(SavedCallsTestCase):
    def test_another_readers_saves_are_never_listed(self):
        call = make_opportunity()
        self.save_as(self.other, call)
        self.assertEqual(self.saved(self.reader), [])

    def test_unsaving_touches_only_the_readers_own_save(self):
        call = make_opportunity()
        self.save_as(self.other, call)
        self.unsave_as(self.reader, call)
        self.assertEqual(len(self.saved(self.other)), 1)

    def test_a_signed_out_visitor_can_neither_list_nor_save(self):
        call = make_opportunity()
        self.client.force_authenticate(None)
        self.assertEqual(self.client.get(reverse("opportunity-saved")).status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(
            self.client.put(reverse("opportunity-save", args=[call.pk])).status_code,
            status.HTTP_401_UNAUTHORIZED,
        )


class OnlyConfirmedTests(SavedCallsTestCase):
    def test_a_missing_call_cant_be_saved(self):
        response = self.as_user(self.reader).put(reverse("opportunity-save", args=[999999]))
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_an_address_that_isnt_a_call_id_is_a_404_not_an_error(self):
        for method in ("put", "delete"):
            with self.subTest(method=method):
                response = getattr(self.as_user(self.reader), method)("/api/v1/opportunities/abc/save/")
                self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_a_waiting_or_rejected_call_cant_be_saved_by_a_reader_its_poster_or_rdco(self):
        for call_status in (CallStatus.PENDING, CallStatus.REJECTED):
            call = make_opportunity(status=call_status, posted_by=self.adviser)
            for user in (self.reader, self.adviser, self.rdco):
                with self.subTest(status=call_status, user=user.email):
                    self.assertEqual(self.save_as(user, call).status_code, status.HTTP_404_NOT_FOUND)
        self.assertFalse(SavedCall.objects.exists())

    def test_a_call_sent_back_to_rdco_or_rejected_is_listed_as_unavailable_with_nothing_more(self):
        for user in (self.reader, self.adviser, self.rdco):
            for call_status in (CallStatus.PENDING, CallStatus.REJECTED):
                with self.subTest(user=user.email, status=call_status):
                    call = make_opportunity(posted_by=self.adviser, title="Hidden title")
                    self.save_as(user, call)
                    Opportunity.objects.filter(pk=call.pk).update(status=call_status)

                    entry = next(e for e in self.saved(user) if e["call_id"] == call.pk)
                    self.assertEqual(entry, {"call_id": call.pk, "available": False})

    def test_it_is_listed_in_full_again_once_confirmed(self):
        call = make_opportunity()
        self.save_as(self.reader, call)
        Opportunity.objects.filter(pk=call.pk).update(status=CallStatus.PENDING)
        Opportunity.objects.filter(pk=call.pk).update(status=CallStatus.CONFIRMED)
        [entry] = self.saved(self.reader)
        self.assertTrue(entry["available"])

    def test_an_unavailable_save_can_still_be_removed(self):
        call = make_opportunity()
        self.save_as(self.reader, call)
        Opportunity.objects.filter(pk=call.pk).update(status=CallStatus.REJECTED)
        self.assertEqual(self.unsave_as(self.reader, call).status_code, status.HTTP_204_NO_CONTENT)
        self.assertEqual(self.saved(self.reader), [])


class AfterTheBoardTests(SavedCallsTestCase):
    def test_a_deleted_call_disappears_from_every_readers_list(self):
        call = make_opportunity(posted_by=self.rdco)
        self.save_as(self.reader, call)
        self.save_as(self.other, call)
        self.as_user(self.rdco).delete(reverse("opportunity-detail", args=[call.pk]))
        self.assertEqual(self.saved(self.reader), [])
        self.assertEqual(self.saved(self.other), [])

    def test_an_over_call_stays_listed_with_its_tags(self):
        call = make_opportunity(title="Last year's", due_date=nov(1), start_date=nov(10), end_date=nov(12))
        self.save_as(self.reader, call)
        with frozen_at(NINE_AM_20TH_MANILA):
            [entry] = self.saved(self.reader)
            board = self.as_user(self.reader).get(reverse("opportunity-list")).data["results"]
        self.assertEqual(board, [])
        self.assertTrue(entry["available"])
        self.assertEqual(entry["call"]["papers_label"], "Submissions closed")
        self.assertEqual(entry["call"]["event_label"], "Event over")


    def test_rdcos_removal_takes_it_off_every_list(self):
        call = make_opportunity(posted_by=self.adviser)
        self.save_as(self.reader, call)
        review.remove(call.pk, by=self.rdco, reason="Cancelled")
        self.assertEqual(self.saved(self.reader), [])

    def test_the_lapse_job_takes_a_lapsed_request_off_every_list(self):
        call = make_opportunity(posted_by=self.adviser, due_date=nov(15))
        self.save_as(self.reader, call)
        Opportunity.objects.filter(pk=call.pk).update(status=CallStatus.PENDING)
        with frozen_at(JUST_AFTER_MIDNIGHT_16TH_MANILA):
            remove_lapsed_requests()
        self.assertFalse(Opportunity.objects.filter(pk=call.pk).exists())
        self.assertEqual(self.saved(self.reader), [])


class IsSavedTests(SavedCallsTestCase):
    def board(self, user):
        return {row["id"]: row for row in self.as_user(user).get(reverse("opportunity-list")).data["results"]}

    def test_the_board_says_which_calls_this_reader_saved(self):
        saved, other = make_opportunity(title="Saved"), make_opportunity(title="Not saved")
        self.save_as(self.reader, saved)
        board = self.board(self.reader)
        self.assertIs(board[saved.pk]["is_saved"], True)
        self.assertIs(board[other.pk]["is_saved"], False)

    def test_another_readers_save_doesnt_mark_it(self):
        call = make_opportunity()
        self.save_as(self.other, call)
        self.assertIs(self.board(self.reader)[call.pk]["is_saved"], False)

    def test_a_calls_own_page_says_so_too_and_unsaving_clears_it(self):
        call = make_opportunity()
        self.save_as(self.reader, call)
        detail = reverse("opportunity-detail", args=[call.pk])
        self.assertIs(self.as_user(self.reader).get(detail).data["is_saved"], True)
        self.unsave_as(self.reader, call)
        self.assertIs(self.as_user(self.reader).get(detail).data["is_saved"], False)

    def test_saving_answers_with_the_call_marked_saved(self):
        call = make_opportunity()
        self.assertIs(self.save_as(self.reader, call).data["call"]["is_saved"], True)
        self.assertIs(self.save_as(self.reader, call).data["call"]["is_saved"], True)

    def test_the_saved_list_marks_its_calls_saved(self):
        call = make_opportunity()
        self.save_as(self.reader, call)
        [entry] = self.saved(self.reader)
        self.assertIs(entry["call"]["is_saved"], True)

    def test_the_board_asks_once_per_page_not_once_per_call(self):
        for n in range(3):
            self.save_as(self.reader, make_opportunity(title=f"Call {n}"))
        with_three = self._board_queries()
        for n in range(3, 8):
            self.save_as(self.reader, make_opportunity(title=f"Call {n}"))
        self.assertEqual(self._board_queries(), with_three)

    def _board_queries(self):
        self.as_user(self.reader)
        with CaptureQueriesContext(connection) as queries:
            self.client.get(reverse("opportunity-list"))
        return len(queries)


class NotAuditedTests(SavedCallsTestCase):
    def test_saving_and_unsaving_write_no_audit_event(self):
        call = make_opportunity()
        before = AuditEvent.objects.count()
        self.save_as(self.reader, call)
        self.unsave_as(self.reader, call)
        self.assertEqual(AuditEvent.objects.count(), before)

    def test_saved_calls_are_not_in_django_admin(self):
        from django.contrib import admin
        self.assertNotIn(SavedCall, admin.site._registry)
