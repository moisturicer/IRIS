"""
Review threads (ADR-032 §7, 2026-11-04 amendment; IR-874).

Anchors, *Must fix* and *Suggestion*, drafts sent by *Finish review*,
*Comment only*, resolving and answering, and what an open *Must fix* blocks.
Every block and refusal is pinned at the REST seam (ADR-032 §12), one class
per acceptance criterion. The migration's backfill is
`test_review_threads_migration.py`.
"""

from django.urls import reverse
from rest_framework import status

from apps.audit.models import AuditEvent
from apps.notifications.models import Notification
from core.enums import (
    ClearanceStatus,
    Party,
    RecordTypeName,
    ResubmissionRequestState,
    SeatState,
    ThreadState,
)

from .models import RecordClearance, Review, ReviewComment, ReviewRound, ReviewThreadEvent
from .test_review_comments import ReviewCommentTestBase, comments_url
from .test_office_review import tracker_url

FIX = "must_fix"
SUGGEST = "suggestion"


def finish_url(record):
    return reverse("record-finish-review", args=[record.pk])


def act_url(record, thread_id, act):
    return reverse("record-review-thread-act", args=[record.pk, thread_id, act])


class ThreadTestBase(ReviewCommentTestBase):

    def thread(self, record, as_user, body="Clarify the sampling in §3.", **extra):
        return self.commented(record, as_user, body, **extra)

    def finish(self, record, as_user, verdict="comment_only", summary="Read it through.", **extra):
        return self.post(finish_url(record), as_user, {"verdict": verdict, "summary": summary, **extra})

    def sent(self, record, as_user, verdict="comment_only", **extra):
        response = self.finish(record, as_user, verdict, **extra)
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        record.refresh_from_db()
        return response.data

    def act(self, record, as_user, thread_id, act, body=None):
        return self.post(act_url(record, thread_id, act), as_user, body or {})

    def must_fix_sent(self, record, as_user, verdict="comment_only", **extra):
        """`as_user` writes one Must fix thread and finishes their review with it."""
        made = self.thread(record, as_user, "Report the response rate.", severity=FIX)
        self.sent(record, as_user, verdict, **extra)
        return made

    def answer(self, record, thread_id, kind="addressed", note="Section 4, p. 12."):
        return self.act(record, self.owner, thread_id, "answer", {"answer": kind, "note": note})

    def ids(self, record, as_user):
        return [c["id"] for c in self.listed(record, as_user).data]

    def readiness(self, record, as_user):
        return self.detail(record, as_user)["readiness"]

    def thread_items(self, record, as_user):
        return [i for i in self.readiness(record, as_user)["items"] if i["kind"] == "open_thread"]

    def itso_open(self):
        record = self.routed(Party.ITSO)
        self.opened_seat(record, Party.ITSO, self.itso)
        return record


# --- AC: existing comments become general Suggestion threads -------------------------
# The backfill itself is `test_review_threads_migration.py`; this pins what a
# general thread is on the wire.

class AThreadOnTheWireTests(ThreadTestBase):

    def test_an_owner_s_thread_is_general_has_no_severity_and_posts_at_once(self):
        record = self.at_adviser_open()

        made = self.thread(record, self.owner, "Is the consent form attached?")

        self.assertFalse(made["is_draft"])
        self.assertIsNone(made["severity"])
        self.assertIsNone(made["party"])
        self.assertEqual(made["party_label"], "The authors")
        self.assertIsNone(made["anchor"])
        self.assertEqual(made["state"], ThreadState.OPEN)
        self.assertIn(made["id"], self.ids(record, self.adviser))

    def test_an_owner_may_not_give_their_thread_a_severity(self):
        record = self.at_adviser_open()

        response = self.comment(record, self.owner, "Mine.", severity=FIX)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_a_reviewer_s_thread_is_a_suggestion_unless_they_choose_must_fix(self):
        record = self.at_adviser_open()

        plain = self.thread(record, self.adviser, "Consider a figure.")
        firm = self.thread(record, self.adviser, "Report the response rate.", severity=FIX)

        self.assertEqual((plain["severity"], plain["party"]), (SUGGEST, Party.ADVISER))
        self.assertEqual(firm["severity"], FIX)
        self.assertEqual(
            self.comment(record, self.adviser, "Hm.", severity="urgent").status_code,
            status.HTTP_400_BAD_REQUEST,
        )

    def test_an_anchored_thread_records_its_passage(self):
        record = self.at_adviser_open()
        anchor = {
            "version": 1, "page": 3, "quote": "forty respondents",
            "prefix": "we surveyed ", "suffix": " in March",
            "regions": [{"page": 3, "left": 0.1, "top": 0.2, "right": 0.6, "bottom": 0.25}],
        }

        made = self.thread(record, self.adviser, "Why forty?", anchor=anchor)

        self.assertEqual(made["anchor"], anchor)

    def test_an_anchor_that_names_no_passage_is_refused(self):
        record = self.at_adviser_open()
        good = {"version": 1, "page": 3, "quote": "forty respondents"}
        for bad in (
            {**good, "version": 9},
            {**good, "page": 0},
            {**good, "quote": "  "},
            {**good, "regions": [{"page": 3, "left": 0.6, "top": 0.2, "right": 0.1, "bottom": 0.3}]},
            {**good, "regions": [{"page": 3, "left": 0.1, "top": 0.2, "right": 1.5, "bottom": 0.3}]},
            "page 3",
        ):
            with self.subTest(anchor=bad):
                self.assertEqual(
                    self.comment(record, self.adviser, "Why?", anchor=bad).status_code,
                    status.HTTP_400_BAD_REQUEST,
                )

    def test_a_reply_has_no_severity_and_no_anchor(self):
        record = self.at_adviser_open()
        question = self.thread(record, self.owner, "Is the consent form attached?")

        for extra in ({"severity": FIX}, {"anchor": {"version": 1, "page": 1, "quote": "x"}}):
            with self.subTest(extra=extra):
                self.assertEqual(
                    self.comment(record, self.adviser, "Yes.", reply_to=question["id"], **extra)
                    .status_code, status.HTTP_400_BAD_REQUEST,
                )


# --- AC: drafts are visible only to their writer ----------------------------------------

class DraftsTests(ThreadTestBase):

    def test_a_seated_reviewer_s_thread_is_seen_by_nobody_else_until_sent(self):
        record = self.itso_open()
        draft = self.thread(record, self.itso, "Check the patent search.")
        self.assertTrue(draft["is_draft"])

        # The writer, and nobody else: owner, Adviser (done), RDCO (seated),
        # and a fellow ITSO member who reads the review from the pool.
        self.assertIn(draft["id"], self.ids(record, self.itso))
        for viewer in (self.owner, self.adviser, self.rdco, self.itso2):
            with self.subTest(viewer=viewer.email):
                self.assertNotIn(draft["id"], self.ids(record, viewer))
                self.client.force_authenticate(viewer)
                tracker = self.client.get(tracker_url(record)).data
                self.assertNotIn("Check the patent search", str(tracker))
                self.assertNotIn("Check the patent search", str(self.detail(record, viewer)))

        self.sent(record, self.itso)

        for viewer in (self.owner, self.adviser, self.rdco, self.itso2):
            with self.subTest(viewer=viewer.email, sent=True):
                self.assertIn(draft["id"], self.ids(record, viewer))

    def test_another_person_s_draft_does_not_exist_for_them(self):
        record = self.itso_open()
        draft = self.thread(record, self.itso, "Check the patent search.")

        for viewer in (self.owner, self.rdco):
            with self.subTest(viewer=viewer.email):
                self.assertEqual(
                    self.edit(record, viewer, draft["id"], "Changed.").status_code,
                    status.HTTP_404_NOT_FOUND,
                )
                self.assertEqual(
                    self.act(record, viewer, draft["id"], "resolve").status_code,
                    status.HTTP_404_NOT_FOUND,
                )
                # A reply to it reads as a reply to nothing in this discussion.
                self.assertEqual(
                    self.comment(record, viewer, "Re.", reply_to=draft["id"]).status_code,
                    status.HTTP_400_BAD_REQUEST,
                )

    def test_the_writer_edits_and_deletes_a_draft_but_never_a_sent_thread(self):
        record = self.at_adviser_open()
        draft = self.thread(record, self.adviser, "Frist draft.")
        self.assertEqual(self.edit(record, self.adviser, draft["id"], "First draft.").status_code, 200)
        self.assertTrue(draft["can_delete"])

        self.client.force_authenticate(self.adviser)
        gone = self.client.delete(reverse("record-review-comment", args=[record.pk, draft["id"]]))
        self.assertEqual(gone.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(ReviewComment.objects.filter(pk=draft["id"]).exists())

        kept = self.thread(record, self.adviser, "Kept.")
        self.sent(record, self.adviser)
        refused = self.client.delete(reverse("record-review-comment", args=[record.pk, kept["id"]]))
        self.assertEqual(refused.status_code, status.HTTP_400_BAD_REQUEST)

    def test_replies_owners_and_former_reviewers_post_at_once(self):
        record = self.itso_open()
        self.cleared(record, self.itso)  # ITSO's part is done
        question = self.thread(record, self.owner, "Is the IP form enough?")

        reply = self.thread(record, self.rdco, "Yes.", reply_to=question["id"])
        former = self.thread(record, self.itso, "One more note.")

        self.assertFalse(reply["is_draft"])
        self.assertEqual((former["is_draft"], former["party"]), (False, Party.ITSO))
        self.assertIn(reply["id"], self.ids(record, self.owner))
        self.assertIn(former["id"], self.ids(record, self.owner))


# --- AC: every verdict goes through its existing service ----------------------------------

class FinishReviewTests(ThreadTestBase):

    def test_comment_only_is_a_round_with_no_outcome(self):
        record = self.itso_open()
        made = self.thread(record, self.itso, "Check the patent search.")

        tracker = self.sent(record, self.itso)

        round_ = ReviewRound.objects.get(record=record)
        self.assertEqual((round_.verdict, round_.party, round_.review), ("comment_only", Party.ITSO, None))
        self.assertEqual(ReviewComment.objects.get(pk=made["id"]).round, round_)
        self.assertFalse(Review.objects.filter(record=record, reviewed_by=self.itso).exists())
        self.assertFalse(RecordClearance.objects.filter(record=record, office=Party.ITSO).exclude(
            status=ClearanceStatus.PENDING).exists())
        self.assertEqual(self.seat_state(record, Party.ITSO, self.itso), SeatState.IN_REVIEW)
        [shown] = tracker["review_rounds"]
        self.assertEqual((shown["verdict"], shown["threads"], shown["version"]), ("comment_only", 1, 1))

    def test_comment_only_tells_each_person_once(self):
        record = self.itso_open()
        for body in ("One.", "Two.", "Three."):
            self.thread(record, self.itso, body)

        with self.captureOnCommitCallbacks(execute=True):
            self.sent(record, self.itso)

        told = list(Notification.objects.filter(record=record, notif_type__name="Review Finished"))
        # The owner, and RDCO's seated reviewer; never the writer.
        self.assertCountEqual([n.recipient_id for n in told], [self.owner.pk, self.rdco.pk])
        self.assertIn("3 comments, no decision", told[0].message)

    def test_comment_only_needs_a_summary_or_a_comment(self):
        record = self.itso_open()

        self.assertEqual(self.finish(record, self.itso, summary="").status_code, status.HTTP_400_BAD_REQUEST)

    def test_request_revision_is_taken_by_the_revision_service(self):
        record = self.itso_open()
        made = self.thread(record, self.itso, "Redo the prior-art search.", severity=FIX)

        self.sent(record, self.itso, "request_revision", summary="Please revise the search.")

        request = record.resubmission_requests.get(state=ResubmissionRequestState.OPEN)
        self.assertEqual((request.party, request.reason), (Party.ITSO, "Please revise the search."))
        round_ = ReviewRound.objects.get(record=record)
        self.assertEqual(round_.review, request.review)
        self.assertFalse(ReviewComment.objects.get(pk=made["id"]).is_draft)

    def test_clear_is_taken_by_the_office_service(self):
        record = self.itso_open()

        self.sent(record, self.itso, "cleared", summary="Nothing patentable.")

        self.assertEqual(self.clearance(record, Party.ITSO), ClearanceStatus.CLEARED)
        self.assertEqual(ReviewRound.objects.get(record=record).review.status, "approved")

    def test_send_to_rdco_is_taken_by_routing(self):
        record = self.at_adviser_open()

        self.sent(record, self.adviser, "send_to_rdco", summary="Sound work.",
                  to=[{"party": Party.RDCO}])

        self.assertIn(Party.RDCO, self.active(record))

    def test_a_decision_is_taken_by_the_decision_service_with_its_token(self):
        record = self.at_rdco()
        token = self.token(record, self.rdco)

        self.sent(record, self.rdco, "keep_unlisted", summary="Kept unlisted.", token=token)

        self.assertEqual(record.pipeline_status, "completed")
        stale = self.finish(record, self.rdco, "reject", token=token)
        self.assertNotEqual(stale.status_code, status.HTTP_200_OK)

    def test_a_verdict_the_caller_may_not_take_is_refused_by_its_own_service(self):
        record = self.at_adviser_open()
        draft = self.thread(record, self.adviser, "Not yet.")

        # The Adviser clears for no office: office-review/'s own 403.
        response = self.finish(record, self.adviser, "cleared")

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        # A refused verdict sends nothing.
        self.assertTrue(ReviewComment.objects.get(pk=draft["id"]).is_draft)
        self.assertFalse(ReviewRound.objects.exists())

    def test_who_finishes_comes_before_what(self):
        record = self.itso_open()

        self.assertEqual(self.finish(record, self.stranger).status_code, status.HTTP_404_NOT_FOUND)
        # ITSO's pool reads the review but holds no seat.
        self.assertEqual(self.finish(record, self.itso2).status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(self.finish(record, self.owner).status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(
            self.finish(record, self.itso, "approve").status_code, status.HTTP_400_BAD_REQUEST,
        )

    def test_an_unopened_seat_is_opened_first(self):
        record = self.new_model()  # the Adviser's seat is still `assigned`

        response = self.finish(record, self.adviser)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["detail"], "Open the review first.")


# --- AC: every block and refusal, at the REST seam -----------------------------------

class WhatMustFixBlocksTests(ThreadTestBase):

    def test_an_approval_that_would_send_a_must_fix_is_refused(self):
        record = self.itso_open()
        self.thread(record, self.itso, "Redo the search.", severity=FIX)

        response = self.finish(record, self.itso, "cleared")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("Must fix", response.data["detail"])

    def test_an_office_s_open_must_fix_blocks_its_clear_and_nothing_else(self):
        record = self.itso_open()
        self.must_fix_sent(record, self.itso)

        clear = self.review(record, self.itso)
        self.assertEqual(clear.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("ITSO has 1 open Must fix thread", clear.data["detail"])
        flags = self.detail(record, self.itso)["office_review"]
        self.assertEqual(flags["clear_blocked"], clear.data["detail"])
        self.assertIsNone(flags["blocked"])
        # A finding doesn't approve.
        self.assertEqual(self.found(record, self.itso).status_code, status.HTTP_200_OK)

    def test_a_finding_is_never_held_by_a_thread(self):
        record = self.itso_open()
        self.must_fix_sent(record, self.itso)

        self.found(record, self.itso)

        self.assertEqual(self.clearance(record, Party.ITSO), ClearanceStatus.NOT_CLEARED)

    def test_a_revision_request_is_never_held_by_a_thread(self):
        record = self.itso_open()
        self.must_fix_sent(record, self.itso)

        self.assertEqual(self.ask(record, self.itso).status_code, status.HTTP_200_OK)

    def test_resolving_or_downgrading_releases_the_clear(self):
        for release in ("resolve", "severity"):
            with self.subTest(release=release):
                record = self.itso_open()
                made = self.must_fix_sent(record, self.itso)
                body = {"severity": SUGGEST} if release == "severity" else None

                self.assertEqual(self.act(record, self.itso, made["id"], release, body).status_code, 200)

                self.assertEqual(self.review(record, self.itso).status_code, status.HTTP_200_OK)

    def test_another_party_s_must_fix_never_blocks_a_clear(self):
        record = self.routed(Party.ITSO, Party.IERC)
        self.opened_seat(record, Party.ITSO, self.itso)
        self.opened_seat(record, Party.IERC, self.ierc)
        self.must_fix_sent(record, self.ierc)

        self.assertEqual(self.review(record, self.itso).status_code, status.HTTP_200_OK)

    def test_the_adviser_s_own_must_fix_blocks_send_to_rdco_but_not_reject(self):
        record = self.at_adviser_open()
        self.must_fix_sent(record, self.adviser)

        send = self.accept(record, [{"party": Party.RDCO}])
        self.assertEqual(send.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(self.detail(record, self.adviser)["routing"]["send_to_rdco_blocked"],
                         send.data["detail"])
        self.assertEqual(self.decide(record, self.adviser, "reject", "Out of scope.").status_code, 200)

    def test_the_adviser_s_own_must_fix_blocks_accepting_a_proposal(self):
        record = self.at_adviser(RecordTypeName.PROPOSAL)
        self.must_fix_sent(record, self.adviser)

        accept = self.decide(record, self.adviser, "accept", "Accepted.")

        self.assertEqual(accept.status_code, status.HTTP_400_BAD_REQUEST)
        flag = self.detail(record, self.adviser)["decision"]
        self.assertEqual(flag["blocked_outcomes"], {"accept": accept.data["detail"]})
        self.assertIsNone(flag["blocked"])

    def test_the_owner_s_next_version_waits_for_an_answer_to_each_must_fix(self):
        record = self.itso_open()
        made = self.must_fix_sent(record, self.itso, "request_revision", summary="Redo the search.")
        self.edit_title(record)

        refused = self.submit_version(record)
        self.assertEqual(refused.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("1 thread from ITSO", refused.data["detail"])
        self.assertEqual(self.detail(record, self.owner)["revision"]["new_version"]["blocked"],
                         refused.data["detail"])

        self.assertEqual(self.answer(record, made["id"]).status_code, status.HTTP_200_OK)
        self.submitted(record)
        # Answering never resolves it: the reviewer does.
        self.assertEqual(ReviewComment.objects.get(pk=made["id"]).state, ThreadState.OPEN)

    def test_a_declined_answer_also_lets_the_version_through(self):
        record = self.itso_open()
        made = self.must_fix_sent(record, self.itso, "request_revision", summary="Redo it.")
        self.edit_title(record)

        self.assertEqual(self.answer(record, made["id"], "declined", "Out of scope.").status_code, 200)

        self.submitted(record)

    def test_only_a_requesting_party_s_must_fix_holds_the_version(self):
        # IERC asked; ITSO's open Must fix is its own, and holds only ITSO's Clear.
        record = self.routed(Party.ITSO, Party.IERC)
        self.opened_seat(record, Party.ITSO, self.itso)
        self.opened_seat(record, Party.IERC, self.ierc)
        self.must_fix_sent(record, self.itso)
        self.asked(record, self.ierc)
        self.edit_title(record)

        self.submitted(record)

    def test_rdco_decides_over_open_must_fix_with_a_reason_and_closes_them(self):
        record = self.at_rdco()
        itso_thread = ReviewComment.objects.create(
            record=record, author=self.itso, body="Prior art?", party=Party.ITSO, severity=FIX,
        )
        no_reason = self.decide(record, self.rdco, "keep_unlisted", "")
        self.assertEqual(no_reason.status_code, status.HTTP_400_BAD_REQUEST)
        flag = self.detail(record, self.rdco)["decision"]
        self.assertTrue(flag["reason_required"])
        self.assertEqual([t["id"] for t in flag["closes"]["threads"]], [itso_thread.pk])

        self.decided(record, self.rdco, "keep_unlisted", "IP is KTTO's to pursue later.")

        itso_thread.refresh_from_db()
        decision = Review.objects.filter(record=record, stage=Party.RDCO).latest("pk")
        self.assertEqual(itso_thread.state, ThreadState.CLOSED)
        self.assertEqual(itso_thread.closed_by_decision, decision)
        self.assertEqual(itso_thread.closed_reason, "IP is KTTO's to pursue later.")
        self.assertTrue(ReviewThreadEvent.objects.filter(thread=itso_thread, kind="closed_by_decision").exists())

    def test_a_thread_opened_after_the_dialog_was_read_makes_the_decision_stale(self):
        record = self.at_rdco()
        token = self.token(record, self.rdco)
        ReviewComment.objects.create(record=record, author=self.itso, body="Late.", party=Party.ITSO,
                                     severity=SUGGEST)

        response = self.decide(record, self.rdco, "keep_unlisted", "Kept.", token=token)

        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)

    def test_rdco_s_own_must_fix_drafts_are_sent_then_closed_by_its_decision(self):
        record = self.at_rdco()
        made = self.thread(record, self.rdco, "Fix the abstract.", severity=FIX)
        token = self.token(record, self.rdco)

        self.sent(record, self.rdco, "keep_unlisted", summary="Kept unlisted.", token=token)

        thread = ReviewComment.objects.get(pk=made["id"])
        self.assertEqual((thread.is_draft, thread.state), (False, ThreadState.CLOSED))

    def test_a_suggestion_never_blocks_anything(self):
        record = self.itso_open()
        self.thread(record, self.itso, "Consider a diagram.")
        self.sent(record, self.itso)

        self.assertEqual(self.review(record, self.itso).status_code, status.HTTP_200_OK)


# --- AC: resolving, reopening, answering, severity ---------------------------------

class ResolvingTests(ThreadTestBase):

    def test_an_owner_resolving_a_reviewer_s_thread_gets_a_403(self):
        record = self.itso_open()
        made = self.must_fix_sent(record, self.itso)

        response = self.act(record, self.owner, made["id"], "resolve")

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertFalse(self.listed(record, self.owner).data[0]["can_resolve"])
        self.assertTrue(self.listed(record, self.owner).data[0]["can_answer"])

    def test_an_owner_resolves_their_own_thread_and_a_reviewer_may_too(self):
        record = self.at_adviser_open()
        mine = self.thread(record, self.owner, "Did I attach the form?")
        theirs = self.thread(record, self.owner, "And the second one?")

        self.assertEqual(self.act(record, self.owner, mine["id"], "resolve").status_code, 200)
        self.assertEqual(self.act(record, self.adviser, theirs["id"], "resolve").status_code, 200)

    def test_any_participant_resolves_and_reopens_a_reviewer_s_thread(self):
        record = self.itso_open()
        made = self.must_fix_sent(record, self.itso)

        resolved = self.act(record, self.rdco, made["id"], "resolve")
        self.assertEqual(resolved.status_code, status.HTTP_200_OK, resolved.data)
        self.assertEqual(resolved.data["state"], ThreadState.RESOLVED)
        self.assertEqual(resolved.data["resolved_by"], self.rdco.get_full_name() or self.rdco.email)

        reopened = self.act(record, self.owner, made["id"], "reopen")
        self.assertEqual(reopened.status_code, status.HTTP_200_OK)
        self.assertEqual(reopened.data["state"], ThreadState.OPEN)
        self.assertEqual(
            [e["kind"] for e in reopened.data["events"]], ["resolved", "reopened"],
        )

    def test_resolving_twice_or_reopening_an_open_thread_is_refused(self):
        record = self.itso_open()
        made = self.must_fix_sent(record, self.itso)

        self.assertEqual(self.act(record, self.itso, made["id"], "reopen").status_code, 400)
        self.act(record, self.itso, made["id"], "resolve")
        self.assertEqual(self.act(record, self.itso, made["id"], "resolve").status_code, 400)

    def test_a_pool_member_reads_but_may_not_resolve_and_a_stranger_sees_nothing(self):
        record = self.itso_open()
        made = self.must_fix_sent(record, self.itso)

        self.assertEqual(self.act(record, self.itso2, made["id"], "resolve").status_code, 403)
        self.assertEqual(self.act(record, self.stranger, made["id"], "resolve").status_code, 404)
        self.assertEqual(self.act(record, self.ierc, made["id"], "reopen").status_code, 404)

    def test_only_the_thread_s_party_changes_its_severity_and_each_change_is_recorded(self):
        record = self.itso_open()
        made = self.must_fix_sent(record, self.itso)

        self.assertEqual(self.act(record, self.rdco, made["id"], "severity", {"severity": SUGGEST})
                         .status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(self.act(record, self.owner, made["id"], "severity", {"severity": SUGGEST})
                         .status_code, status.HTTP_403_FORBIDDEN)
        changed = self.act(record, self.itso, made["id"], "severity", {"severity": SUGGEST})

        self.assertEqual(changed.status_code, status.HTTP_200_OK)
        [event] = changed.data["events"]
        self.assertEqual((event["kind"], event["from"], event["to"]), ("severity_changed", FIX, SUGGEST))

    def test_the_party_owns_the_thread_not_the_person(self):
        record = self.itso_open()
        made = self.must_fix_sent(record, self.itso)
        # A colleague seated for ITSO later owns the same thread.
        self.opened_seat(record, Party.ITSO, self.itso2)

        response = self.act(record, self.itso2, made["id"], "severity", {"severity": SUGGEST})

        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_only_an_owner_answers_and_an_answer_says_where_or_why(self):
        record = self.itso_open()
        made = self.must_fix_sent(record, self.itso)

        self.assertEqual(self.act(record, self.itso, made["id"], "answer",
                                  {"answer": "addressed", "note": "p. 4"}).status_code, 403)
        self.assertEqual(self.answer(record, made["id"], "addressed", " ").status_code, 400)
        self.assertEqual(self.answer(record, made["id"], "done", "p. 4").status_code, 400)
        answered = self.answer(record, made["id"], "declined", "Out of scope for a capstone.")

        self.assertEqual(answered.status_code, status.HTTP_200_OK)
        self.assertEqual(answered.data["answer"]["kind"], "declined")
        self.assertEqual(answered.data["state"], ThreadState.OPEN)

    def test_an_owner_s_own_thread_needs_no_answer(self):
        record = self.at_adviser_open()
        mine = self.thread(record, self.owner, "Note to self.")

        self.assertEqual(self.answer(record, mine["id"]).status_code, status.HTTP_400_BAD_REQUEST)


# --- AC: capabilities and readiness match the refusals --------------------------------

class ReadinessMatchesTheRefusalsTests(ThreadTestBase):

    def test_an_office_s_must_fix_is_a_blocker_to_it_and_information_to_others(self):
        record = self.itso_open()
        self.must_fix_sent(record, self.itso)

        [mine] = self.thread_items(record, self.itso)
        self.assertEqual(mine["severity"], "blocker")
        self.assertEqual(self.review(record, self.itso).status_code, 400)
        [theirs] = self.thread_items(record, self.owner)
        self.assertEqual(theirs["severity"], "info")
        self.assertEqual(theirs["label"], "ITSO has 1 open Must fix thread.")

    def test_rdco_is_told_a_decision_closes_them(self):
        record = self.at_rdco()
        ReviewComment.objects.create(record=record, author=self.itso, body="Prior art?",
                                     party=Party.ITSO, severity=FIX)

        [item] = self.thread_items(record, self.rdco)

        self.assertEqual(item["severity"], "info")
        self.assertIn("A Decision now closes them", item["label"])
        self.assertEqual(self.readiness(record, self.rdco)["verdict"], "ready")

    def test_an_unanswered_must_fix_is_the_owner_s_blocker_until_answered(self):
        record = self.itso_open()
        made = self.must_fix_sent(record, self.itso, "request_revision", summary="Redo it.")
        self.edit_title(record)

        [item] = self.thread_items(record, self.owner)
        self.assertEqual(item["severity"], "blocker")
        self.assertEqual(item["label"], "Answer ITSO's 1 open Must fix thread before you submit v2.")
        self.assertEqual(self.submit_version(record).status_code, 400)

        self.answer(record, made["id"])
        [item] = self.thread_items(record, self.owner)
        self.assertEqual(item["severity"], "info")

    def test_the_adviser_s_must_fix_blocks_its_send_and_says_so(self):
        record = self.at_adviser_open()
        self.must_fix_sent(record, self.adviser)

        [item] = self.thread_items(record, self.adviser)

        self.assertEqual(item["severity"], "blocker")
        self.assertIn("finish_review", self.detail(record, self.adviser)["capabilities"])
        self.assertEqual(self.accept(record, [{"party": Party.RDCO}]).status_code, 400)

    def test_suggestions_alone_are_information(self):
        record = self.itso_open()
        self.thread(record, self.itso, "Consider a diagram.")
        self.sent(record, self.itso)

        [item] = self.thread_items(record, self.itso)

        self.assertEqual((item["severity"], item["label"]), ("info", "ITSO has 1 open suggestion."))

    def test_a_reader_who_may_not_read_the_review_is_told_nothing(self):
        record = self.itso_open()
        self.must_fix_sent(record, self.itso)
        self.client.force_authenticate(self.stranger)

        self.assertEqual(self.client.get(comments_url(record)).status_code, 404)


# --- AC: audit events ------------------------------------------------------------------

class AuditTests(ThreadTestBase):

    def events(self, record, event_type):
        return list(AuditEvent.objects.filter(record=record, event_type=event_type).order_by("pk"))

    def test_finishing_a_review_is_audited_comment_only_included(self):
        record = self.itso_open()
        made = self.must_fix_sent(record, self.itso)

        [event] = self.events(record, AuditEvent.REVIEW_FINISHED)

        self.assertEqual(event.user, self.itso)
        self.assertEqual(event.metadata["verdict"], "comment_only")
        self.assertEqual(event.metadata["threads"], [made["id"]])
        self.assertEqual((event.metadata["must_fix"], event.metadata["review"]), (1, None))
        self.assertNotIn("Read it through", str(event.metadata))  # no review prose

    def test_resolve_reopen_severity_and_answer_are_audited(self):
        record = self.itso_open()
        made = self.must_fix_sent(record, self.itso)

        self.act(record, self.itso, made["id"], "severity", {"severity": SUGGEST})
        self.answer(record, made["id"], "addressed", "Section 4.")
        self.act(record, self.itso, made["id"], "resolve")
        self.act(record, self.owner, made["id"], "reopen")

        [changed] = self.events(record, AuditEvent.REVIEW_THREAD_SEVERITY_CHANGED)
        self.assertEqual((changed.metadata["previous"], changed.metadata["severity"]), (FIX, SUGGEST))
        [answered] = self.events(record, AuditEvent.REVIEW_THREAD_ANSWERED)
        self.assertNotIn("Section 4", str(answered.metadata))
        self.assertEqual(len(self.events(record, AuditEvent.REVIEW_THREAD_RESOLVED)), 1)
        self.assertEqual(len(self.events(record, AuditEvent.REVIEW_THREAD_REOPENED)), 1)

    def test_a_decision_closing_threads_is_audited(self):
        record = self.at_rdco()
        thread = ReviewComment.objects.create(record=record, author=self.itso, body="Prior art?",
                                              party=Party.ITSO, severity=FIX)

        self.decided(record, self.rdco, "keep_unlisted", "Kept.")

        [event] = self.events(record, AuditEvent.REVIEW_THREADS_CLOSED)
        self.assertEqual((event.metadata["threads"], event.metadata["must_fix"]), ([thread.pk], 1))


# --- review follow-ups: what a Decision closes, and the one notification ---------------

class DecisionClosesWhatItListedTests(ThreadTestBase):

    def test_the_adviser_s_reject_closes_open_threads_too(self):
        record = self.at_adviser_open()
        made = self.must_fix_sent(record, self.adviser)
        mine = self.thread(record, self.owner, "Did I attach the form?")

        self.decided(record, self.adviser, "reject", "Out of scope for this programme.")

        for thread_id in (made["id"], mine["id"]):
            thread = ReviewComment.objects.get(pk=thread_id)
            self.assertEqual(thread.state, ThreadState.CLOSED)
            self.assertEqual(thread.closed_reason, "Out of scope for this programme.")

    def test_a_proposal_decision_closes_open_threads(self):
        record = self.at_adviser(RecordTypeName.PROPOSAL)
        made = self.thread(record, self.adviser, "Consider a pilot.")
        self.sent(record, self.adviser)

        self.decided(record, self.adviser, "accept", "Accepted.")

        self.assertEqual(ReviewComment.objects.get(pk=made["id"]).state, ThreadState.CLOSED)

    def test_a_direct_decision_sends_and_closes_the_drafts_its_dialog_listed(self):
        # decide/ without Finish review: the dialog listed RDCO's own draft as
        # closing and asked for a reason because of it, so it closes it.
        record = self.at_rdco()
        made = self.thread(record, self.rdco, "Fix the abstract.", severity=FIX)
        flag = self.detail(record, self.rdco)["decision"]
        self.assertTrue(flag["reason_required"])
        self.assertEqual([t["id"] for t in flag["closes"]["threads"]], [made["id"]])

        self.decided(record, self.rdco, "keep_unlisted", "Kept unlisted.")

        thread = ReviewComment.objects.get(pk=made["id"])
        self.assertEqual((thread.is_draft, thread.state), (False, ThreadState.CLOSED))
        self.assertIn(made["id"], self.ids(record, self.owner))

    def test_another_reviewer_s_draft_is_not_closed_or_sent(self):
        record = self.at_rdco()
        theirs = ReviewComment.objects.create(
            record=record, author=self.rdco2, body="Unsent.", party=Party.RDCO,
            severity=FIX, is_draft=True,
        )

        self.decided(record, self.rdco, "keep_unlisted", "")

        theirs.refresh_from_db()
        self.assertEqual((theirs.is_draft, theirs.state), (True, ThreadState.OPEN))


class OneNotificationTests(ThreadTestBase):

    def test_a_verdict_s_own_notice_is_the_only_one(self):
        record = self.itso_open()
        for body in ("One.", "Two."):
            self.thread(record, self.itso, body, severity=FIX)

        with self.captureOnCommitCallbacks(execute=True):
            self.sent(record, self.itso, "request_revision", summary="Please revise.")

        owner_notices = Notification.objects.filter(record=record, recipient=self.owner)
        self.assertEqual(owner_notices.count(), 1)
        notice = owner_notices.get()
        self.assertEqual(notice.notif_type.name, "Revision Requested")
        # The verdict's own notice counts what came with it.
        self.assertTrue(notice.message.endswith("The review came with 2 comments."), notice.message)
        self.assertFalse(Notification.objects.filter(notif_type__name="Review Finished").exists())

    def owner_messages(self, record):
        return [n.message for n in Notification.objects.filter(record=record, recipient=self.owner)]

    def test_a_decision_s_notice_counts_its_comments(self):
        record = self.at_rdco()
        self.thread(record, self.rdco, "Tighten the abstract.")
        token = self.token(record, self.rdco)

        with self.captureOnCommitCallbacks(execute=True):
            self.sent(record, self.rdco, "keep_unlisted", summary="Kept.", token=token)

        [message] = [m for m in self.owner_messages(record) if "kept it unlisted" in m]
        self.assertTrue(message.endswith("The review came with 1 comment."), message)

    def test_send_to_rdco_tells_the_owners_with_the_count(self):
        record = self.at_adviser_open()
        self.thread(record, self.adviser, "Nice work on §2.")

        with self.captureOnCommitCallbacks(execute=True):
            self.sent(record, self.adviser, "send_to_rdco", summary="Sound.", to=[{"party": Party.RDCO}])

        [message] = self.owner_messages(record)
        self.assertIn("Your Adviser accepted", message)
        self.assertTrue(message.endswith("The review came with 1 comment."), message)

    def test_an_office_completing_counts_its_comments_in_its_outcome_notice(self):
        record = self.itso_open()
        self.thread(record, self.itso, "Prior art looks clear.")

        with self.captureOnCommitCallbacks(execute=True):
            self.sent(record, self.itso, "cleared", summary="Nothing patentable.")

        [message] = self.owner_messages(record)
        self.assertIn("ITSO finished its review", message)
        self.assertTrue(message.endswith("The review came with 1 comment."), message)

    def test_an_office_verdict_that_completes_nothing_tells_only_of_its_comments(self):
        # Two ITSO seats: the first Clear completes nothing, so no outcome is
        # announced (IR-269), and the comments it sent are told on their own.
        record = self.itso_open()
        self.opened_seat(record, Party.ITSO, self.itso2)
        self.thread(record, self.itso, "One.")
        self.thread(record, self.itso, "Two.")

        with self.captureOnCommitCallbacks(execute=True):
            self.sent(record, self.itso, "cleared", summary="Nothing patentable.")

        [message] = self.owner_messages(record)
        self.assertEqual(message, f'ITSO sent 2 comments on v1 of "{record.title}".')
        self.assertNotIn("cleared", message.lower())

    def test_a_verdict_with_no_comments_reads_as_before(self):
        record = self.itso_open()

        with self.captureOnCommitCallbacks(execute=True):
            self.sent(record, self.itso, "request_revision", summary="Please revise.")

        [message] = self.owner_messages(record)
        self.assertNotIn("came with", message)


class DraftsAndStrangersTests(ThreadTestBase):

    def test_a_stranger_reads_neither_the_draft_nor_the_discussion(self):
        record = self.itso_open()
        self.thread(record, self.itso, "Check the patent search.")
        self.client.force_authenticate(self.stranger)

        self.assertEqual(self.client.get(comments_url(record)).status_code, status.HTTP_404_NOT_FOUND)
        tracker = self.client.get(tracker_url(record))
        if tracker.status_code == status.HTTP_200_OK:
            self.assertIsNone(tracker.data["review_comments"])
            self.assertIsNone(tracker.data["review_rounds"])
