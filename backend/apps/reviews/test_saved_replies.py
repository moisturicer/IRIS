"""
Saved replies at the REST seam (ADR-032 §7, 2026-11-04 Conveniences; IR-877).

A person keeps their own reusable texts and inserts one into a comment. What
this pins:

* the owner is always the caller: another person's reply is never listed,
  changed or removed, and answers the same 404 as one that does not exist;
* a title is needed and is unique per person, ignoring case;
* the text is bounded like a review comment;
* the number kept is bounded.
"""

from rest_framework.test import APITestCase

from apps.accounts.models import User

from .comments import MAX_BODY_LENGTH
from .models import MAX_SAVED_REPLIES, MAX_SAVED_REPLY_TITLE, SavedReply

REPLIES = "/api/v1/reviews/saved-replies/"


def reply_url(pk):
    return f"{REPLIES}{pk}/"


class SavedReplyTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.ana = User.objects.create_user(email="ana@cit.edu", password="x", first_name="Ana")
        cls.ben = User.objects.create_user(email="ben@cit.edu", password="x", first_name="Ben")

    def setUp(self):
        self.client.force_authenticate(self.ana)

    def make(self, title="Cite the source", body="Please cite where this figure comes from."):
        return self.client.post(REPLIES, {"title": title, "body": body}, format="json")

    # -- create, list, edit, delete ------------------------------------------

    def test_a_person_saves_a_reply_and_finds_it_listed(self):
        response = self.make()

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["title"], "Cite the source")
        self.assertEqual(response.data["body"], "Please cite where this figure comes from.")
        listed = self.client.get(REPLIES).data
        self.assertEqual(listed["limit"], MAX_SAVED_REPLIES)
        self.assertEqual(
            [(r["id"], r["title"], r["body"]) for r in listed["results"]],
            [(response.data["id"], "Cite the source", "Please cite where this figure comes from.")],
        )

    def test_replies_are_listed_by_title(self):
        self.make("Typo")
        self.make("almost there")
        self.make("Methods unclear")

        titles = [r["title"] for r in self.client.get(REPLIES).data["results"]]

        self.assertEqual(titles, ["almost there", "Methods unclear", "Typo"])

    def test_the_owner_edits_the_title_and_the_text(self):
        pk = self.make().data["id"]

        response = self.client.patch(reply_url(pk), {"title": "Source?", "body": "Where is this from?"},
                                     format="json")

        self.assertEqual(response.status_code, 200)
        self.assertEqual((response.data["title"], response.data["body"]), ("Source?", "Where is this from?"))
        self.assertEqual(SavedReply.objects.get(pk=pk).body, "Where is this from?")

    def test_the_owner_deletes_one(self):
        pk = self.make().data["id"]

        self.assertEqual(self.client.delete(reply_url(pk)).status_code, 204)
        self.assertEqual(self.client.get(REPLIES).data["results"], [])

    # -- private to their owner -----------------------------------------------

    def test_another_persons_replies_are_never_listed(self):
        self.make()
        self.client.force_authenticate(self.ben)

        self.assertEqual(self.client.get(REPLIES).data["results"], [])

    def test_another_persons_reply_is_the_same_404_as_a_missing_one(self):
        pk = self.make().data["id"]
        self.client.force_authenticate(self.ben)

        for response in (
            self.client.patch(reply_url(pk), {"title": "Mine now"}, format="json"),
            self.client.delete(reply_url(pk)),
            self.client.patch(reply_url(pk + 1000), {"title": "Mine now"}, format="json"),
            self.client.delete(reply_url(pk + 1000)),
        ):
            self.assertEqual(response.status_code, 404)
            self.assertEqual(response.data, {"detail": "Not found."})
        self.assertEqual(SavedReply.objects.get(pk=pk).title, "Cite the source")

    def test_nobody_signed_out_reaches_them(self):
        self.client.force_authenticate(None)

        self.assertIn(self.client.get(REPLIES).status_code, (401, 403))

    # -- what a reply may hold -------------------------------------------------

    def test_a_title_and_a_text_are_needed(self):
        self.assertEqual(self.make(title="  ").status_code, 400)
        self.assertEqual(self.make(body="  ").status_code, 400)
        self.assertEqual(self.make(title=None).status_code, 400)

    def test_a_title_is_unique_per_person_ignoring_case(self):
        self.make("Typo")

        response = self.make("typo")

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["title"], ["You already have a saved reply with that title."])
        # Someone else may use the same title.
        self.client.force_authenticate(self.ben)
        self.assertEqual(self.make("Typo").status_code, 201)

    def test_renaming_onto_another_title_is_refused(self):
        self.make("Typo")
        pk = self.make("Grammar").data["id"]

        response = self.client.patch(reply_url(pk), {"title": "TYPO"}, format="json")

        self.assertEqual(response.status_code, 400)
        # Keeping its own title, in another case, is fine.
        self.assertEqual(
            self.client.patch(reply_url(pk), {"title": "grammar"}, format="json").status_code, 200,
        )

    def test_the_text_is_bounded_like_a_comment(self):
        self.assertEqual(self.make(body="x" * MAX_BODY_LENGTH).status_code, 201)
        self.assertEqual(self.make("Long", body="x" * (MAX_BODY_LENGTH + 1)).status_code, 400)

    def test_the_title_is_bounded(self):
        self.assertEqual(self.make(title="t" * (MAX_SAVED_REPLY_TITLE + 1)).status_code, 400)

    def test_an_edit_names_something_to_change(self):
        pk = self.make().data["id"]

        self.assertEqual(self.client.patch(reply_url(pk), {}, format="json").status_code, 400)

    def test_the_number_kept_is_bounded(self):
        SavedReply.objects.bulk_create(
            SavedReply(owner=self.ana, title=f"Reply {i}", body="Text")
            for i in range(MAX_SAVED_REPLIES)
        )

        response = self.make("One too many")

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["code"], "saved_reply_limit")
