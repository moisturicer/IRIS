"""
Viewed marks at the REST seam (ADR-032 §7 Conveniences and its IR-877 build
notes; ADR-058 §3 as amended, point 7).

A person ticks a compared section as viewed. What this pins:

* a mark follows its text: the section's `text_hash`, in whichever Version or
  reading it is found, so an unchanged section stays Viewed into a later
  Version and a section a later Version changes reads not viewed;
* a mark records the reading and the Version it was made on;
* a comparison made with another reading of the same Version carries a mark
  only where the section's `text_hash` matches, and says nothing about readings;
* marks are private: nobody else sees them, and anyone the review does not
  admit is told nothing.
"""
from unittest.mock import patch

from django.urls import reverse
from rest_framework import status

from apps.records.models import ReviewText, ReviewTextSection
from apps.records.test_review_text import ReviewTextTestBase, V2
from apps.records.test_review_text_readings import QUEUE, next_reader
from apps.records.review_text import store
from apps.records.review_text.testing import THESIS, in_process_sandbox, pdf
from core.enums import Party

from .models import ViewedMark

V3_PAGES = [page[:] for page in THESIS]
V3_PAGES[1] = V3_PAGES[1][:-1] + [("para", ["This study asks whether two plants are feasible."])]
# v3 rewrites the background as well; v2's problem statement stays.
V3_PAGES[1][3] = ("para", ["Metro Cebu generates about 3,000 tonnes of waste a day."])
V3 = pdf(V3_PAGES)

SANDBOX = "apps.records.review_text.sandbox.read_in_sandbox"

BACKGROUND = "background of the study"
PROBLEM = "statement of the problem"
#: A heading with no text of its own before its first subsection.
INTRODUCTION = "introduction"
LITERATURE = "review of related literature"


def compare_url(record):
    return reverse("record-version-compare", args=[record.pk])


def viewed_url(record):
    return reverse("record-version-compare-viewed", args=[record.pk])


class ViewedTestBase(ReviewTextTestBase):

    def two_versions(self):
        record = self.thesis(Party.IERC)
        self.resubmitted(record, body=V2)
        self.read_all(record)
        return record

    def third_version(self, record, body=V3):
        """IERC asks again; the owner uploads `body` and submits v3."""
        self.asked(record, self.ierc)
        self.owner_uploads(record, body)
        with patch("apps.records.tasks.read_review_text.delay"), \
                patch("apps.documents.tasks.extract_manuscript_text.delay"):
            self.submitted(record)
        self.read_all(record)

    def compare(self, record, user, pair=(1, 2)):
        self.client.force_authenticate(user)
        with patch(QUEUE):
            response = self.client.get(compare_url(record), {"from": pair[0], "to": pair[1]})
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual(response.data["state"], "ready", response.data)
        return response.data

    def viewed(self, record, user, pair=(1, 2)) -> dict:
        """Each section's key on the side it is marked on → whether it reads Viewed."""
        out = {}
        for section in self.compare(record, user, pair)["sections"]:
            side = section["to"] or section["from"]
            out[side["key"]] = section["viewed"]
        return out

    def mark(self, record, user, key, *, viewed=True, pair=(1, 2), side="to"):
        self.client.force_authenticate(user)
        with patch(QUEUE):
            return self.client.post(viewed_url(record), {
                "from": pair[0], "to": pair[1], "side": side, "key": key, "viewed": viewed,
            }, format="json")


class MarkingTests(ViewedTestBase):

    def test_a_reviewer_marks_a_section_viewed_and_the_comparison_says_so(self):
        record = self.two_versions()

        response = self.mark(record, self.ierc, PROBLEM)

        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual(response.data, {"viewed": True})
        viewed = self.viewed(record, self.ierc)
        self.assertTrue(viewed[PROBLEM])
        self.assertFalse(viewed[BACKGROUND])

    def test_a_mark_records_its_reading_its_version_and_the_sections_text_hash(self):
        record = self.two_versions()
        v2 = self.version(record, 2)

        self.mark(record, self.ierc, PROBLEM)

        mark = ViewedMark.objects.get()
        section = ReviewTextSection.objects.get(text=v2.review_text, key=PROBLEM)
        self.assertEqual((mark.user, mark.record, mark.version, mark.reading),
                         (self.ierc, record, v2, v2.review_text))
        self.assertEqual((mark.section_key, mark.text_hash), (PROBLEM, section.text_hash))

    def test_marking_twice_keeps_one_mark(self):
        record = self.two_versions()
        self.mark(record, self.ierc, PROBLEM)
        self.mark(record, self.ierc, PROBLEM)

        self.assertEqual(ViewedMark.objects.count(), 1)

    def test_unmarking_clears_it(self):
        record = self.two_versions()
        self.mark(record, self.ierc, PROBLEM)

        response = self.mark(record, self.ierc, PROBLEM, viewed=False)

        self.assertEqual(response.data, {"viewed": False})
        self.assertFalse(self.viewed(record, self.ierc)[PROBLEM])

    def test_a_removed_section_is_marked_on_its_earlier_side(self):
        record = self.two_versions()
        # v2's text loses a section: drop Chapter 2's literature review from its reading.
        text = self.version(record, 2).review_text
        gone = ReviewTextSection.objects.filter(text=text).order_by("-ordinal").first()

        gone_key = gone.key
        gone.delete()
        response = self.mark(record, self.ierc, gone_key, side="from")

        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertTrue(self.viewed(record, self.ierc)[gone_key])


class EmptySectionTests(ViewedTestBase):
    """A section with no text has the hash of nothing, so its text can't tell
    it apart from another empty one: it is matched by its key as well."""

    def test_marking_one_empty_section_does_not_tick_another(self):
        record = self.two_versions()
        intro = ReviewTextSection.objects.get(text=self.version(record, 2).review_text, key=INTRODUCTION)
        ReviewTextSection.objects.filter(text=self.version(record, 2).review_text, key=LITERATURE)             .update(passages=[], text_hash=intro.text_hash)

        self.mark(record, self.ierc, INTRODUCTION)
        viewed = self.viewed(record, self.ierc)

        self.assertTrue(viewed[INTRODUCTION])
        self.assertFalse(viewed[LITERATURE])
        # Unticking it leaves the other alone, too.
        self.mark(record, self.ierc, LITERATURE)
        self.mark(record, self.ierc, INTRODUCTION, viewed=False)
        viewed = self.viewed(record, self.ierc)
        self.assertEqual((viewed[INTRODUCTION], viewed[LITERATURE]), (False, True))


class FollowsItsTextTests(ViewedTestBase):
    """AC: a mark clears when a later Version changes the section."""

    def test_an_unchanged_section_stays_viewed_into_a_later_version_and_a_changed_one_clears(self):
        record = self.two_versions()
        self.mark(record, self.ierc, PROBLEM)
        self.mark(record, self.ierc, BACKGROUND)
        self.third_version(record)

        viewed = self.viewed(record, self.ierc, pair=(2, 3))

        # v3 kept v2's problem statement, so it is still the text that was viewed.
        self.assertTrue(viewed[PROBLEM])
        # v3 rewrote the background: the mark doesn't carry.
        self.assertFalse(viewed[BACKGROUND])

    def test_the_mark_still_shows_on_the_comparison_it_was_made_on(self):
        record = self.two_versions()
        self.mark(record, self.ierc, BACKGROUND)
        self.third_version(record)

        self.assertTrue(self.viewed(record, self.ierc, pair=(1, 2))[BACKGROUND])


class OtherReadingTests(ViewedTestBase):
    """AC: another reading of the same Version carries a mark only where the
    section's `text_hash` matches, and nothing says a reading changed."""

    def newer_readings(self, record, differ=()):
        """Deploy a newer reader and read both Versions again, then make the
        newer readings differ from the originals in the `differ` sections."""
        with next_reader():
            with patch(QUEUE):
                self.client.force_authenticate(self.ierc)
                self.client.get(compare_url(record), {"from": 1, "to": 2})
            with patch(SANDBOX, side_effect=in_process_sandbox):
                for text in ReviewText.objects.filter(record=record, state="pending"):
                    store.read_text(text.pk)
        originals = [self.version(record, n).review_text_id for n in (1, 2)]
        ReviewTextSection.objects.filter(key__in=differ).exclude(text_id__in=originals) \
            .update(text_hash="0" * 64)

    def test_a_mark_carries_to_a_newer_reading_only_where_the_text_hash_matches(self):
        record = self.two_versions()
        self.mark(record, self.ierc, PROBLEM)
        self.mark(record, self.ierc, BACKGROUND)
        self.newer_readings(record, differ=[BACKGROUND])

        with next_reader():
            viewed = self.viewed(record, self.ierc)

        self.assertTrue(viewed[PROBLEM])
        self.assertFalse(viewed[BACKGROUND])

    def test_nothing_in_the_comparison_names_a_reading(self):
        record = self.two_versions()
        self.mark(record, self.ierc, PROBLEM)
        self.newer_readings(record, differ=[PROBLEM])

        with next_reader():
            data = self.compare(record, self.ierc)

        self.assertEqual(set(data["sections"][0]),
                         {"status", "renamed", "moved", "from", "to", "changes", "counts", "viewed"})
        self.assertNotIn("reader", str(data))
        self.assertNotIn("reading", str(data))


class PrivacyTests(ViewedTestBase):
    """AC: nobody else can read a mark."""

    def test_another_reader_of_the_review_never_sees_my_marks(self):
        record = self.two_versions()
        self.mark(record, self.ierc, PROBLEM)

        self.assertFalse(self.viewed(record, self.ierc2)[PROBLEM])
        self.assertFalse(self.viewed(record, self.owner)[PROBLEM])

    def test_an_owner_marks_their_own(self):
        record = self.two_versions()

        self.assertEqual(self.mark(record, self.owner, BACKGROUND).status_code, status.HTTP_200_OK)
        self.assertTrue(self.viewed(record, self.owner)[BACKGROUND])
        self.assertFalse(self.viewed(record, self.ierc)[BACKGROUND])

    def test_someone_the_review_does_not_admit_is_told_nothing(self):
        record = self.two_versions()

        response = self.mark(record, self.stranger, PROBLEM)

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertFalse(ViewedMark.objects.exists())


class RefusalTests(ViewedTestBase):

    def test_a_section_the_comparison_does_not_have_is_refused(self):
        record = self.two_versions()

        response = self.mark(record, self.ierc, "No such heading")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_a_malformed_request_is_refused(self):
        record = self.two_versions()
        self.client.force_authenticate(self.ierc)

        for body in ({"from": 1, "to": 2, "side": "middle", "key": PROBLEM, "viewed": True},
                     {"from": 1, "to": 2, "side": "to", "key": PROBLEM, "viewed": "yes"},
                     {"from": 1, "to": 2, "side": "to", "viewed": True},
                     {"from": 1, "side": "to", "key": PROBLEM, "viewed": True}):
            with patch(QUEUE):
                response = self.client.post(viewed_url(record), body, format="json")
            self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST, body)
        self.assertFalse(ViewedMark.objects.exists())

    def test_a_comparison_still_being_prepared_is_refused(self):
        record = self.thesis(Party.IERC)
        self.resubmitted(record, body=V2)   # neither Version read yet

        response = self.mark(record, self.ierc, PROBLEM)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
