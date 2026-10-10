"""
Who may edit a record's details and submit it, when, and what stays fixed
(IR-507, ADR-032 §10 Amendment of 2026-10-11).

Until IR-507 the record update and `submit/` were `IsOwnerOrStaff`: an office
could edit any record it could see and submit a student's draft, recording the
staff member as the one who gave the student's Data Privacy Act consent, and an
owner could edit in every state. Settled with the project lead:

1. only an owner edits details or submits -- any owner, not only the primary;
2. an owner edits only a `draft`, or a record awaiting their revision;
3. once submitted, `versions.SUBMISSION_FIXED_FIELDS` stay as submitted -- an
   unchanged value is accepted, a change is one 400 naming every field.

Refusals follow ADR-022 §Amendment 4: 403 for a record the caller can see.
"""

from django.urls import reverse
from rest_framework import status

from apps.records.models import Record, RecordOwner, RecordType
from apps.records.versions import SUBMISSION_FIXED_FIELDS
from apps.reviews.test_decisions import DecisionTestBase
from core.enums import Party, PipelineStatus, RecordTypeName


def detail_url(record):
    return reverse("record-detail", args=[record.pk])


def submit_url(record):
    return reverse("record-submit", args=[record.pk])


class EditPolicyTestBase(DecisionTestBase):

    def edit(self, record, as_user, body):
        self.client.force_authenticate(as_user)
        return self.client.patch(detail_url(record), body, format="json")

    def submit(self, record, as_user):
        return self.post(submit_url(record), as_user, {"dpa_accepted": True})

    def published(self):
        record = self.at_adviser()
        self.decided(record, self.adviser, "publish")
        return record

    def awaiting_revision(self):
        """In review at its Adviser, who has asked the owner for a revision."""
        record = self.at_adviser()
        self.asked(record, self.adviser)
        return record


# --- who ------------------------------------------------------------------------------

class OnlyAnOwnerEditsTests(EditPolicyTestBase):

    def test_no_office_edits_a_record_that_is_not_theirs(self):
        """A draft, a record in review, a published one: every office sees all three."""
        for state in ("make_record", "at_adviser", "published"):
            record = getattr(self, state)()
            title = record.title
            for office in (self.itso, self.ierc, self.rdco):
                with self.subTest(state=state, office=office.email):
                    response = self.edit(record, office, {"title": "An office's own title"})

                    self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN, response.data)
                    record.refresh_from_db()
                    self.assertEqual(record.title, title)

    def test_the_adviser_does_not_edit_the_record_they_review(self):
        record = self.at_adviser()

        response = self.edit(record, self.adviser, {"title": "The adviser's own title"})

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN, response.data)

    def test_any_owner_edits_not_only_the_primary_one(self):
        record = self.make_record()
        RecordOwner.objects.create(record=record, user=self.reader, is_primary=False)

        response = self.edit(record, self.reader, {"title": "A co-author's better title"})

        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)


class OnlyAnOwnerSubmitsTests(EditPolicyTestBase):

    def test_neither_an_office_nor_the_adviser_submits_a_draft(self):
        record = self.make_record()
        for user in (self.itso, self.rdco, self.adviser):
            with self.subTest(user=user.email):
                response = self.submit(record, user)

                self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN, response.data)
        record.refresh_from_db()
        self.assertEqual(record.pipeline_status, PipelineStatus.DRAFT)
        self.assertIsNone(record.dpa_accepted_by)

    def test_a_co_owner_submits_and_the_consent_is_theirs(self):
        record = self.make_record()
        RecordOwner.objects.create(record=record, user=self.reader, is_primary=False)

        response = self.submit(record, self.reader)

        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        record.refresh_from_db()
        self.assertEqual(record.dpa_accepted_by, self.reader)


# --- when -----------------------------------------------------------------------------

class WhenAnOwnerEditsTests(EditPolicyTestBase):

    def test_an_owner_edits_a_draft_including_what_is_fixed_later(self):
        record = self.make_record()
        proposal = RecordType.objects.get_or_create(name=RecordTypeName.PROPOSAL)[0]

        response = self.edit(record, self.owner, {
            "title": "A draft's better title",
            "adviser": self.other_adviser.pk,
            "record_type": proposal.pk,
            "is_ip": True,
        })

        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        record.refresh_from_db()
        self.assertEqual((record.adviser, record.record_type, record.is_ip), (self.other_adviser, proposal, True))

    def test_an_owner_edits_details_while_a_revision_is_asked_for(self):
        record = self.awaiting_revision()

        response = self.edit(record, self.owner, {"title": "The revised title"})

        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        record.refresh_from_db()
        self.assertEqual(record.title, "The revised title")

    def test_an_owner_does_not_edit_a_record_in_review_with_no_revision_asked_for(self):
        record = self.at_adviser()
        title = record.title

        response = self.edit(record, self.owner, {"title": "Changed under the reviewer"})

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST, response.data)
        record.refresh_from_db()
        self.assertEqual(record.title, title)

    def test_an_owner_does_not_edit_a_published_record(self):
        """Post-publication correction is deferred, not built (ADR-032 §10 Amendment)."""
        record = self.published()

        response = self.edit(record, self.owner, {"title": "Changed after acceptance"})

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST, response.data)


# --- what -----------------------------------------------------------------------------

class FixedOnceSubmittedTests(EditPolicyTestBase):

    def test_the_fixed_fields_are_the_routing_and_ip_judgement_ones(self):
        """The list is the decision; changing it is an ADR amendment, not a refactor."""
        self.assertEqual(set(SUBMISSION_FIXED_FIELDS), {
            "adviser", "record_type",
            "is_ip", "for_commercialization", "community_extension",
            "requested_itso", "requested_ierc", "requested_ktto", "requires_ethics_review",
        })

    def test_changing_the_adviser_mid_review_is_refused_naming_it(self):
        record = self.awaiting_revision()

        response = self.edit(record, self.owner, {"adviser": self.other_adviser.pk})

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST, response.data)
        self.assertEqual(set(response.data), {"adviser"})
        record.refresh_from_db()
        self.assertEqual(record.adviser, self.adviser)

    def test_every_changed_fixed_field_is_named_in_one_refusal(self):
        record = self.awaiting_revision()
        proposal = RecordType.objects.get_or_create(name=RecordTypeName.PROPOSAL)[0]

        response = self.edit(record, self.owner, {
            "title": "Saved only if nothing fixed changes",
            "adviser": self.other_adviser.pk,
            "record_type": proposal.pk,
            "is_ip": not record.is_ip,
            "requested_ierc": not record.requested_ierc,
        })

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST, response.data)
        self.assertEqual(set(response.data), {"adviser", "record_type", "is_ip", "requested_ierc"})
        record.refresh_from_db()
        self.assertNotEqual(record.title, "Saved only if nothing fixed changes")

    def test_sending_the_fixed_fields_unchanged_is_accepted(self):
        """What Edit details used to send on every save: the whole form."""
        record = self.awaiting_revision()

        response = self.edit(record, self.owner, {
            "title": "The revised title",
            "adviser": self.adviser.pk,
            "is_ip": record.is_ip,
            "requires_ethics_review": record.requires_ethics_review,
            "for_commercialization": record.for_commercialization,
        })

        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        record.refresh_from_db()
        self.assertEqual(record.title, "The revised title")

    def test_an_office_tagged_ip_flag_survives_the_owner_s_revision(self):
        """`tags/` is the offices' once a record is submitted; an owner's save cannot undo it."""
        record = self.awaiting_revision()
        Record.objects.filter(pk=record.pk).update(is_ip=True)

        response = self.edit(record, self.owner, {"is_ip": False})

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST, response.data)
        record.refresh_from_db()
        self.assertTrue(record.is_ip)


class WhatAChangedAdviserWouldStrandTests(EditPolicyTestBase):
    """
    Why `adviser` is fixed (IR-507): the Adviser seat stays with the Adviser
    the record entered with, while routing asks who `record.adviser` is now.
    Changed behind the seat's back -- here by the ORM, since the API now
    refuses it -- neither Adviser can accept and route it to an office: the
    old one no longer matches `record.adviser`, the new one holds no seat.
    """

    def test_neither_the_old_nor_the_new_adviser_can_act(self):
        record = self.at_adviser()
        Record.objects.filter(pk=record.pk).update(adviser=self.other_adviser)
        to = [{"party": Party.ITSO}]

        for adviser in (self.adviser, self.other_adviser):
            with self.subTest(adviser=adviser.email):
                response = self.accept(record, to, as_user=adviser)

                self.assertIn(response.status_code, (status.HTTP_403_FORBIDDEN, status.HTTP_404_NOT_FOUND))
        self.assertEqual(self.active(record), {Party.ADVISER})
