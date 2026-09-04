"""
Tests for apps.opportunities (IR-121).

Written alongside the endpoints, not after: IR-120 found six endpoints in this
codebase enforcing less than they declared, so the permission matrix here is
pinned per-action rather than assumed from reading get_permissions().

No pytest is configured for this repo -- these use rest_framework's APITestCase.
Run with:

    docker compose exec -T backend python manage.py test apps.opportunities
"""
from datetime import date, timedelta

from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from apps.accounts.models import Role, User

from .models import Opportunity
from .services import build_ics


def make_user(email, role_name=None, **extra):
    role = Role.objects.get_or_create(name=role_name)[0] if role_name else None
    return User.objects.create_user(
        email=email, password="pw12345!", first_name="Test", last_name="User",
        role=role, is_verified=True, **extra,
    )


def make_opportunity(**overrides):
    fields = {
        "opportunity_type": Opportunity.TYPE_INSTITUTIONAL_GRANT,
        "title":            "CIT-U Seed Grant",
        "posting_office":   "Research & Development Coordinating Office (RDCO)",
        "audience":         "CIT-U Faculty Researchers",
        "description":      "Competitive institutional seed funding.",
        "due_date":         date.today() + timedelta(days=28),
        "tags":             ["Seed Grant"],
    }
    fields.update(overrides)
    return Opportunity.objects.create(**fields)


class OpportunityPermissionTests(APITestCase):
    """
    Browsing is open to any authenticated user; publishing is limited to
    RDCO, KTTO and Adviser.

    Students must never be able to post -- an unvetted "funding call" carrying
    an external link is a phishing vector aimed at the whole institution.
    """

    def setUp(self):
        self.student = make_user("student@cit.edu", "Student")
        self.adviser = make_user("adviser@cit.edu", "Adviser")
        self.rdco    = make_user("rdco@cit.edu",    "RDCO")
        self.ktto    = make_user("ktto@cit.edu",    "KTTO")
        self.itso    = make_user("itso@cit.edu",    "ITSO")
        self.opportunity = make_opportunity()

        self.list_url   = reverse("opportunity-list")
        self.detail_url = reverse("opportunity-detail", args=[self.opportunity.pk])

    def _payload(self, **overrides):
        payload = {
            "opportunity_type": Opportunity.TYPE_INTERNAL_CALL,
            "title":            "Departmental Call for Capstone Proposals",
            "posting_office":   "College of Computer Studies",
            "audience":         "All Undergraduate Thesis Students",
            "description":      "Submit capstone proposals for review.",
            "due_date":         str(date.today() + timedelta(days=14)),
            "tags":             ["Capstone"],
        }
        payload.update(overrides)
        return payload

    def test_anonymous_cannot_browse(self):
        self.assertIn(
            self.client.get(self.list_url).status_code,
            (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN),
        )

    def test_any_authenticated_user_can_browse(self):
        for user in (self.student, self.adviser, self.rdco, self.itso):
            self.client.force_authenticate(user)
            self.assertEqual(self.client.get(self.list_url).status_code, status.HTTP_200_OK)

    def test_student_cannot_create(self):
        self.client.force_authenticate(self.student)
        response = self.client.post(self.list_url, self._payload(), format="json")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(Opportunity.objects.count(), 1)

    def test_itso_cannot_create(self):
        """ITSO is in STAFF_ROLES but is deliberately NOT a poster."""
        self.client.force_authenticate(self.itso)
        response = self.client.post(self.list_url, self._payload(), format="json")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_poster_roles_can_create(self):
        for user in (self.rdco, self.ktto, self.adviser):
            self.client.force_authenticate(user)
            response = self.client.post(self.list_url, self._payload(), format="json")
            self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)

    def test_student_cannot_update_or_delete(self):
        self.client.force_authenticate(self.student)
        self.assertEqual(
            self.client.patch(self.detail_url, {"title": "Hijacked"}, format="json").status_code,
            status.HTTP_403_FORBIDDEN,
        )
        self.assertEqual(self.client.delete(self.detail_url).status_code, status.HTTP_403_FORBIDDEN)
        self.opportunity.refresh_from_db()
        self.assertEqual(self.opportunity.title, "CIT-U Seed Grant")

    def test_posted_by_is_the_request_user_not_client_supplied(self):
        """A poster must not be able to attribute a call to somebody else."""
        self.client.force_authenticate(self.rdco)
        response = self.client.post(
            self.list_url, self._payload(posted_by=self.adviser.pk), format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(Opportunity.objects.get(pk=response.data["id"]).posted_by, self.rdco)


class OpportunityVisibilityTests(APITestCase):
    """Closed items grey out in place, then drop off once nobody can act."""

    def setUp(self):
        self.user = make_user("browser@cit.edu", "Student")
        self.client.force_authenticate(self.user)

    def test_open_and_recently_closed_are_listed_but_stale_are_not(self):
        open_item   = make_opportunity(title="Open",   due_date=date.today() + timedelta(days=5))
        closing_today  = make_opportunity(title="Today",  due_date=date.today())
        recent      = make_opportunity(title="Recent", due_date=date.today() - timedelta(days=3))
        stale       = make_opportunity(title="Stale",  due_date=date.today() - timedelta(days=90))

        titles = [row["title"] for row in self.client.get(reverse("opportunity-list")).data["results"]]
        self.assertIn(open_item.title, titles)
        self.assertIn(closing_today.title, titles)
        self.assertIn(recent.title, titles)
        self.assertNotIn(stale.title, titles)

    def test_days_left_and_is_closed_are_served(self):
        make_opportunity(title="Past", due_date=date.today() - timedelta(days=2))
        row = next(
            r for r in self.client.get(reverse("opportunity-list")).data["results"]
            if r["title"] == "Past"
        )
        self.assertEqual(row["days_left"], -2)
        self.assertTrue(row["is_closed"])

    def test_featured_sorts_before_a_sooner_deadline(self):
        make_opportunity(title="Soon",     due_date=date.today() + timedelta(days=1))
        make_opportunity(title="Featured", due_date=date.today() + timedelta(days=40), is_featured=True)
        titles = [r["title"] for r in self.client.get(reverse("opportunity-list")).data["results"]]
        self.assertLess(titles.index("Featured"), titles.index("Soon"))


class IcsExportTests(APITestCase):
    """The calendar file is the reminder mechanism, so its escaping matters."""

    def setUp(self):
        self.user = make_user("cal@cit.edu", "Student")
        self.client.force_authenticate(self.user)

    def test_endpoint_returns_a_calendar_attachment(self):
        opportunity = make_opportunity()
        response = self.client.get(reverse("opportunity-calendar", args=[opportunity.pk]))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("text/calendar", response["Content-Type"])
        self.assertIn("attachment", response["Content-Disposition"])

        body = response.content.decode()
        self.assertTrue(body.startswith("BEGIN:VCALENDAR"))
        self.assertIn("END:VEVENT", body)
        self.assertIn(f"UID:iris-opportunity-{opportunity.pk}@cit.edu", body)

    def test_commas_and_semicolons_in_a_title_are_escaped(self):
        """
        "Robotics, AI & Sensors; Phase 2" is an ordinary title, and both
        separators are structural in RFC 5545 -- unescaped, they corrupt the
        event rather than merely looking wrong.
        """
        opportunity = make_opportunity(title="Robotics, AI & Sensors; Phase 2")
        body = build_ics(opportunity)
        summary = next(line for line in body.split("\r\n") if line.startswith("SUMMARY:"))
        self.assertIn("Robotics\\, AI & Sensors\\; Phase 2", summary)

    def test_all_day_event_ends_the_following_day(self):
        """DTEND is exclusive; equal DTSTART/DTEND is dropped by some clients."""
        due = date.today() + timedelta(days=10)
        body = build_ics(make_opportunity(due_date=due))
        self.assertIn(f"DTSTART;VALUE=DATE:{due.strftime('%Y%m%d')}", body)
        self.assertIn(f"DTEND;VALUE=DATE:{(due + timedelta(days=1)).strftime('%Y%m%d')}", body)

    def test_uses_crlf_line_endings(self):
        self.assertIn("\r\n", build_ics(make_opportunity()))


class TagValidationTests(APITestCase):
    def setUp(self):
        self.rdco = make_user("rdco2@cit.edu", "RDCO")
        self.client.force_authenticate(self.rdco)

    def _payload(self, tags):
        return {
            "opportunity_type": Opportunity.TYPE_FUNDING_WINDOW,
            "title":            "DOST-PCIEERD Call",
            "posting_office":   "External Grants Liaison / KTTO",
            "due_date":         str(date.today() + timedelta(days=43)),
            "tags":             tags,
        }

    def test_non_string_tags_are_rejected(self):
        response = self.client.post(reverse("opportunity-list"), self._payload([1, 2]), format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_blank_tags_are_stripped(self):
        response = self.client.post(
            reverse("opportunity-list"), self._payload(["  Agri  ", "", "  "]), format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["tags"], ["Agri"])
