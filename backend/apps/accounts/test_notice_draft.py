"""
RDCO's saved draft of the next data notice (IR-1138): one draft for the whole
system, RDCO only, replaced on every save and removed by a publish. It is
never a version and never reaches anyone else.
"""
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from apps.accounts.models import DataNotice, NoticeDraft
from apps.records.tests import make_user


class NoticeDraftTests(APITestCase):
    def setUp(self):
        self.rdco = make_user("nd_rdco@cit.edu", "RDCO")
        self.url = reverse("notice-draft")
        self.base = DataNotice.current().number

    def as_(self, user):
        self.client.force_authenticate(user)

    def test_there_is_no_draft_until_one_is_saved(self):
        self.as_(self.rdco)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIsNone(response.data)

    def test_saving_keeps_the_paste_exactly_and_replaces_the_last(self):
        self.as_(self.rdco)
        self.client.put(self.url, {"based_on_version": self.base, "text": "first"}, format="json")
        text = "  line one\n\n  <b>two</b>"
        saved = self.client.put(self.url, {"based_on_version": self.base, "text": text}, format="json")

        self.assertEqual(saved.status_code, status.HTTP_200_OK)
        self.assertEqual(NoticeDraft.objects.count(), 1)
        read = self.client.get(self.url).data
        self.assertEqual(read["text"], text)
        self.assertEqual(read["based_on_version"], self.base)

    def test_a_draft_is_not_a_version(self):
        self.as_(self.rdco)
        self.client.put(self.url, {"based_on_version": self.base, "text": "draft"}, format="json")
        self.assertEqual(DataNotice.current().number, self.base)

    def test_publishing_removes_the_draft(self):
        self.as_(self.rdco)
        self.client.put(self.url, {"based_on_version": self.base, "text": "next"}, format="json")
        published = self.client.post(
            reverse("notice-versions"), {"based_on_version": self.base, "text": "next"}, format="json",
        )
        self.assertEqual(published.status_code, status.HTTP_201_CREATED)
        self.assertIsNone(self.client.get(self.url).data)

    def test_discarding_removes_it(self):
        self.as_(self.rdco)
        self.client.put(self.url, {"based_on_version": self.base, "text": "x"}, format="json")
        self.assertEqual(self.client.delete(self.url).status_code, status.HTTP_204_NO_CONTENT)
        self.assertIsNone(self.client.get(self.url).data)

    def test_anyone_else_is_refused_and_a_draft_is_not_read_by_them(self):
        self.as_(self.rdco)
        self.client.put(self.url, {"based_on_version": self.base, "text": "secret"}, format="json")
        for email, role in (("nd_s@cit.edu", "Student"), ("nd_itso@cit.edu", "ITSO"), ("nd_sa@cit.edu", "System Admin")):
            self.as_(make_user(email, role))
            self.assertEqual(self.client.get(self.url).status_code, status.HTTP_403_FORBIDDEN, role)
            self.assertEqual(
                self.client.put(self.url, {"based_on_version": self.base, "text": "x"}, format="json").status_code,
                status.HTTP_403_FORBIDDEN, role,
            )
            self.assertEqual(self.client.delete(self.url).status_code, status.HTTP_403_FORBIDDEN, role)
        self.assertEqual(NoticeDraft.objects.get().text, "secret")
