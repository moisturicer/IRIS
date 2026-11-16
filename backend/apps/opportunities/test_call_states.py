"""
IR-761: a Call's two states, and when it is Over (ADR-050 decisions 6 and 7).

Each case pins a boundary day with a literal from the decision, not a value
recomputed the way the model computes it.
"""
from datetime import date, datetime, timezone as dt_timezone
from unittest.mock import patch

from django.test import SimpleTestCase
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from .models import Opportunity
from .tests import make_opportunity, make_user


def nov(day):
    return date(2026, 11, day)


def call(due, start=None, end=None):
    """An unsaved Conference; the rules read only its dates."""
    return Opportunity(
        opportunity_type=Opportunity.TYPE_CONFERENCE, title="A call",
        due_date=due, start_date=start, end_date=end,
    )


class CallStateTests(SimpleTestCase):
    # (description, call, today, papers, event, over)
    CASES = [
        # Both event dates: deadline the 10th, event the 20th to the 22nd.
        ("both, deadline day", call(nov(10), nov(20), nov(22)), nov(10), "accepting", "upcoming", False),
        ("both, day after deadline", call(nov(10), nov(20), nov(22)), nov(11), "closed", "upcoming", False),
        ("both, day before start", call(nov(10), nov(20), nov(22)), nov(19), "closed", "upcoming", False),
        ("both, start day", call(nov(10), nov(20), nov(22)), nov(20), "closed", "happening", False),
        ("both, end day", call(nov(10), nov(20), nov(22)), nov(22), "closed", "happening", False),
        ("both, day after end", call(nov(10), nov(20), nov(22)), nov(23), "closed", "over", True),
        # Start date only: a one-day event.
        ("start only, deadline day", call(nov(10), nov(20)), nov(10), "accepting", "upcoming", False),
        ("start only, day after deadline", call(nov(10), nov(20)), nov(11), "closed", "upcoming", False),
        ("start only, day before", call(nov(10), nov(20)), nov(19), "closed", "upcoming", False),
        ("start only, the day", call(nov(10), nov(20)), nov(20), "closed", "happening", False),
        ("start only, day after", call(nov(10), nov(20)), nov(21), "closed", "over", True),
        # End date only: never Happening now (owner, 2026-11-15).
        ("end only, end day", call(nov(10), end=nov(22)), nov(22), "closed", "upcoming", False),
        ("end only, day after", call(nov(10), end=nov(22)), nov(23), "closed", "over", True),
        ("end only, deadline after, day after end", call(nov(25), end=nov(22)), nov(23), "accepting", "over", False),
        ("end only, deadline after, day after deadline", call(nov(25), end=nov(22)), nov(26), "closed", "over", True),
        # No event dates: no event state until Over, the day after the deadline.
        ("none, deadline day", call(nov(10)), nov(10), "accepting", None, False),
        ("none, day after deadline", call(nov(10)), nov(11), "closed", "over", True),
        # End mistyped before start: the latest date entered decides.
        ("end before start, end day", call(nov(10), nov(20), nov(18)), nov(18), "closed", "upcoming", False),
        ("end before start, start day", call(nov(10), nov(20), nov(18)), nov(20), "closed", "happening", False),
        ("end before start, day after start", call(nov(10), nov(20), nov(18)), nov(21), "closed", "over", True),
        # Deadline after the event: the event is over and papers are still
        # accepted (owner, 2026-11-15); the Call is not Over until the deadline.
        ("deadline after event, end day", call(nov(25), nov(20), nov(22)), nov(22), "accepting", "happening", False),
        ("deadline after event, day after end", call(nov(25), nov(20), nov(22)), nov(23), "accepting", "over", False),
        ("deadline after event, deadline day", call(nov(25), nov(20), nov(22)), nov(25), "accepting", "over", False),
        ("deadline after event, day after deadline", call(nov(25), nov(20), nov(22)), nov(26), "closed", "over", True),
        # Deadline during the event: both states at once.
        ("deadline during event", call(nov(21), nov(20), nov(22)), nov(21), "accepting", "happening", False),
    ]

    def test_each_boundary_day(self):
        for description, opportunity, today, papers, event, over in self.CASES:
            with self.subTest(description):
                self.assertEqual(opportunity.papers_state(today), papers)
                self.assertEqual(opportunity.event_state(today), event)
                self.assertEqual(opportunity.is_over(today), over)

    def test_each_state_has_a_label(self):
        opportunity = call(nov(10), nov(20), nov(22))
        self.assertEqual(opportunity.papers_label(nov(10)), "Accepting papers")
        self.assertEqual(opportunity.papers_label(nov(11)), "Submissions closed")
        self.assertEqual(opportunity.event_label(nov(19)), "Upcoming")
        self.assertEqual(opportunity.event_label(nov(20)), "Happening now")
        self.assertEqual(opportunity.event_label(nov(23)), "Event over")
        self.assertIsNone(call(nov(10)).event_label(nov(10)))

    def test_a_call_with_no_event_reads_over_not_event_over(self):
        self.assertEqual(call(nov(10)).event_label(nov(11)), "Over")

    def test_an_event_over_beside_accepting_papers(self):
        opportunity = call(nov(25), nov(20), nov(22))
        self.assertEqual(opportunity.papers_label(nov(23)), "Accepting papers")
        self.assertEqual(opportunity.event_label(nov(23)), "Event over")


#: Noon on 2026-11-15 in Manila (UTC+8).
NOON_15TH_MANILA = datetime(2026, 11, 15, 4, 0, tzinfo=dt_timezone.utc)
#: 01:00 on the 16th in Manila, while it is still the 15th in UTC.
EARLY_16TH_MANILA = datetime(2026, 11, 15, 17, 0, tzinfo=dt_timezone.utc)


def frozen_at(moment):
    return patch("django.utils.timezone.now", return_value=moment)


class CallStatesApiTests(APITestCase):
    """The board reads both states from the server, and drops a Call once it is Over."""

    def setUp(self):
        self.rdco = make_user("rdco@cit.edu", "RDCO")
        self.client.force_authenticate(self.rdco)
        clock = frozen_at(NOON_15TH_MANILA)
        clock.start()
        self.addCleanup(clock.stop)

    def _listed(self):
        response = self.client.get(reverse("opportunity-list"))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        return {row["title"]: row for row in response.data["results"]}

    def test_the_list_carries_both_states_and_their_labels(self):
        make_opportunity(title="Open", due_date=nov(20), start_date=nov(25), end_date=nov(27))
        make_opportunity(title="On now", due_date=nov(1), start_date=nov(14), end_date=nov(16))
        make_opportunity(title="Journal", opportunity_type=Opportunity.TYPE_JOURNAL, due_date=nov(30))

        rows = self._listed()
        self.assertEqual(
            {k: rows["Open"][k] for k in ("papers_state", "papers_label", "event_state", "event_label")},
            {"papers_state": "accepting", "papers_label": "Accepting papers",
             "event_state": "upcoming", "event_label": "Upcoming"},
        )
        self.assertEqual(
            {k: rows["On now"][k] for k in ("papers_state", "papers_label", "event_state", "event_label")},
            {"papers_state": "closed", "papers_label": "Submissions closed",
             "event_state": "happening", "event_label": "Happening now"},
        )
        self.assertIsNone(rows["Journal"]["event_state"])
        self.assertIsNone(rows["Journal"]["event_label"])

    def test_the_list_leaves_out_over_calls_and_keeps_one_on_its_last_day(self):
        make_opportunity(title="Deadline yesterday", due_date=nov(14))
        make_opportunity(title="Event ended yesterday", due_date=nov(1), start_date=nov(12), end_date=nov(14))
        make_opportunity(title="Deadline today", due_date=nov(15))
        make_opportunity(title="Event ends today", due_date=nov(1), start_date=nov(13), end_date=nov(15))
        # Closed 45 days ago, so the old 30-day rule would have hidden it.
        make_opportunity(title="Event ahead", due_date=date(2026, 10, 1), start_date=nov(20))
        # End mistyped before start: the start date still keeps it listed.
        make_opportunity(title="Mistyped end", due_date=nov(1), start_date=nov(20), end_date=nov(3))
        # Event over, papers still accepted: listed until the deadline.
        make_opportunity(title="Event over, papers open", due_date=nov(20), start_date=nov(10), end_date=nov(12))

        rows = self._listed()
        self.assertEqual(
            set(rows),
            {"Deadline today", "Event ends today", "Event ahead", "Mistyped end", "Event over, papers open"},
        )
        self.assertEqual(
            (rows["Event over, papers open"]["papers_label"], rows["Event over, papers open"]["event_label"]),
            ("Accepting papers", "Event over"),
        )

    def test_an_over_call_is_still_reachable_off_the_board(self):
        """Detail, edit, delete and the calendar still reach it, so a mistyped date can be fixed."""
        over = make_opportunity(title="Over", due_date=nov(1), posted_by=self.rdco)
        detail = reverse("opportunity-detail", args=[over.pk])

        response = self.client.get(detail)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["event_state"], "over")
        self.assertEqual(response.data["event_label"], "Over")

        calendar = self.client.get(reverse("opportunity-calendar", args=[over.pk]))
        self.assertEqual(calendar.status_code, status.HTTP_200_OK)
        self.assertIn("DTSTART;VALUE=DATE:20261101", calendar.content.decode())

        edited = self.client.patch(detail, {"due_date": "2026-11-30"}, format="json")
        self.assertEqual(edited.status_code, status.HTTP_200_OK)
        self.assertEqual(edited.data["papers_state"], "accepting")
        self.assertIn("Over", self._listed())

        self.assertEqual(self.client.delete(detail).status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(Opportunity.objects.filter(pk=over.pk).exists())


class ManilaDateTests(APITestCase):
    """"Today" is Manila's date, not the server's: CI and the containers run in UTC."""

    def test_a_deadline_of_the_15th_reads_closed_at_1am_on_the_16th_in_manila(self):
        self.client.force_authenticate(make_user("student@cit.edu", "Student"))
        make_opportunity(title="Due the 15th", due_date=nov(15), start_date=nov(20))
        make_opportunity(title="No event, due the 15th", due_date=nov(15))

        with frozen_at(EARLY_16TH_MANILA):
            rows = {
                row["title"]: row
                for row in self.client.get(reverse("opportunity-list")).data["results"]
            }

        self.assertEqual(rows["Due the 15th"]["papers_state"], "closed")
        self.assertIs(rows["Due the 15th"]["is_closed"], True)
        self.assertEqual(rows["Due the 15th"]["days_left"], -1)
        self.assertNotIn("No event, due the 15th", rows)
