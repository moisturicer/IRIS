"""
IR-786: a person downloads a copy of their own data (ADR-051 decision 13).

Three kinds of test live here:

* **The declaration test** fails when a model that holds a person's data is not
  named in `personal_data.registry`, as included or as deliberately excluded.
  That is what keeps the download from silently falling behind the schema.
* **The content tests** pin what the file holds and, more to the point, what it
  does not: another owner, the Adviser, someone else's review comment, a
  credential, a Turn resting on a paper the person can no longer read.
* **The endpoint tests** cover the request: signed in, audited, rate-limited,
  never cached.

The per-role outcomes are also in the authorization matrix
(`apps/tests/access/table.py`, `user-me-data`).

**Seam: the API.** The registry tests read the model graph.
"""

import json
from unittest import mock

from django.core.cache import cache
from rest_framework.test import APITestCase

from apps.accounts.models import AccountDeletionRequest, Role, RoleRequest, User
from apps.accounts.personal_data import SECTIONS
from apps.accounts.personal_data import registry
from apps.accounts.throttles import PersonalDataExportThrottle
from apps.ai.models import Conversation, Turn, TurnCitation
from apps.audit.models import AuditEvent
from apps.library.models import SavedRecord
from apps.notifications.models import Notification, NotificationRead, NotificationType
from apps.records.models import (
    Author, DeleteRequest, DiscoveryDismissal, DownloadRequest, Record, RecordOwner, RecordType,
)
from apps.reviews.models import Review, ReviewComment
from core.enums import Party, PipelineStatus, ReadingStatus, RequestStatus, ReviewVerdict, RoleName

URL = "/api/v1/users/me/data/"

SECRET = "TestPass123!"


def _user(email, role_name=RoleName.STUDENT, **extra):
    role = Role.objects.get_or_create(name=role_name)[0]
    return User.objects.create_user(
        email=email, password=SECRET, first_name=email.split("@")[0].title(),
        last_name="Person", role=role, is_verified=True, consent_given=True, **extra,
    )


def _paper(title, owner, *, adviser=None, status=PipelineStatus.DRAFT, **extra):
    record = Record.objects.create(
        title=title, abstract="An abstract about " + title,
        record_type=RecordType.objects.get_or_create(name="Thesis / Research")[0],
        added_by=owner, adviser=adviser, pipeline_status=status, **extra,
    )
    RecordOwner.objects.create(record=record, user=owner, is_primary=True)
    return record


def _text(response):
    return json.dumps(response.json())


class DeclarationTests(APITestCase):
    """The export cannot silently fall behind the models."""

    def test_every_model_that_holds_a_persons_data_is_declared(self):
        missing = registry.undeclared()
        self.assertEqual(
            missing, set(),
            "These models point at a person (directly, or by cascading from a model that "
            "does) and the personal-data export does not say what it does with them: "
            f"{sorted(missing)}. Add each to INCLUDED (with the export section that carries "
            "it) or to EXCLUDED (with the reason it is left out) in "
            "apps/accounts/personal_data/registry.py.",
        )

    def test_a_model_left_out_of_both_lists_is_reported(self):
        included = {k: v for k, v in registry.INCLUDED.items() if k != "library.SavedRecord"}
        self.assertEqual(registry.undeclared(included, registry.EXCLUDED), {"library.SavedRecord"})

    def test_a_model_with_no_user_column_is_found_through_its_parent(self):
        # A Turn has no user column: it cascades from a Conversation, which has.
        self.assertIn("ai.Turn", registry.personal_data_models())
        self.assertIn("ai.TurnCitation", registry.personal_data_models())

    def test_nothing_is_declared_twice(self):
        self.assertEqual(set(registry.INCLUDED) & set(registry.EXCLUDED), set())

    def test_nothing_declared_is_stale(self):
        from django.apps import apps

        real = {model._meta.label for model in apps.get_models()}
        stale = (set(registry.INCLUDED) | set(registry.EXCLUDED)) - real
        self.assertEqual(stale, set(), f"declared but no longer a model: {sorted(stale)}")

    def test_every_included_model_names_a_section_the_export_builds(self):
        unknown = {label: section for label, section in registry.INCLUDED.items() if section not in SECTIONS}
        self.assertEqual(unknown, {})

    def test_every_section_is_fed_by_a_declared_model(self):
        fed = set(registry.INCLUDED.values())
        # `consent` reads fields of the account and the paper, not a model of its own.
        self.assertEqual(set(SECTIONS) - fed - {"consent"}, set())

    def test_every_exclusion_gives_a_reason(self):
        blank = [label for label, why in registry.EXCLUDED.items() if len(why.strip()) < 20]
        self.assertEqual(blank, [])

    def test_credential_models_are_excluded(self):
        for label in ("accounts.RecoveryToken", "accounts.RecoveryIntent",
                      "token_blacklist.OutstandingToken", "token_blacklist.BlacklistedToken"):
            with self.subTest(model=label):
                self.assertIn(label, registry.EXCLUDED)


class ExportEndpointTests(APITestCase):

    @classmethod
    def setUpTestData(cls):
        cls.me = _user("me@cit.edu")
        cls.other = _user("other@cit.edu")

    def setUp(self):
        cache.clear()

    def test_it_needs_a_signed_in_caller(self):
        self.assertEqual(self.client.get(URL).status_code, 401)

    def test_it_is_a_json_download_that_is_never_cached(self):
        self.client.force_authenticate(self.me)
        response = self.client.get(URL)
        self.assertEqual(response.status_code, 200)
        self.assertIn("application/json", response["Content-Type"])
        self.assertIn("attachment", response["Content-Disposition"])
        cache_control = response["Cache-Control"]
        for directive in ("no-store", "private"):
            self.assertIn(directive, cache_control)

    def test_there_is_no_way_to_name_another_person(self):
        self.client.force_authenticate(self.me)
        for suffix in ("?user=%d" % self.other.pk, "?id=%d" % self.other.pk):
            with self.subTest(query=suffix):
                body = self.client.get(URL + suffix).json()
                self.assertEqual(body["account"]["email"], "me@cit.edu")

    def test_a_download_is_audited_without_its_contents(self):
        self.client.force_authenticate(self.me)
        self.client.get(URL)
        event = AuditEvent.objects.get(event_type=AuditEvent.PERSONAL_DATA_EXPORTED)
        self.assertEqual(event.user, self.me)
        self.assertEqual(set(event.metadata), {"format", "sections"})
        self.assertNotIn("me@cit.edu", json.dumps(event.metadata))

    def test_a_refused_request_is_not_audited_as_a_download(self):
        self.client.get(URL)
        self.assertFalse(AuditEvent.objects.filter(event_type=AuditEvent.PERSONAL_DATA_EXPORTED).exists())

    def test_downloads_are_rate_limited_per_person(self):
        rates = {**PersonalDataExportThrottle.THROTTLE_RATES, "personal_data_export": "2/hour"}
        with mock.patch.object(PersonalDataExportThrottle, "THROTTLE_RATES", rates):
            self.client.force_authenticate(self.me)
            self.assertEqual(self.client.get(URL).status_code, 200)
            self.assertEqual(self.client.get(URL).status_code, 200)
            self.assertEqual(self.client.get(URL).status_code, 429)
            # Another person has a budget of their own.
            self.client.force_authenticate(self.other)
            self.assertEqual(self.client.get(URL).status_code, 200)
        self.assertEqual(
            AuditEvent.objects.filter(event_type=AuditEvent.PERSONAL_DATA_EXPORTED).count(), 3,
        )

    def test_every_role_gets_its_own_copy(self):
        for role in RoleName.values:
            with self.subTest(role=role):
                person = _user(f"{role.lower()}-who@cit.edu", role)
                self.client.force_authenticate(person)
                response = self.client.get(URL)
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json()["account"]["email"], person.email)


class ExportContentTests(APITestCase):
    """What the file holds, and what it must not."""

    @classmethod
    def setUpTestData(cls):
        cls.me = _user("me@cit.edu")
        cls.coowner = _user("coowner@cit.edu")
        cls.adviser = _user("adviser@cit.edu", RoleName.ADVISER)
        cls.stranger = _user("stranger@cit.edu")
        cls.paper = _paper("My thesis on mangroves", cls.me, adviser=cls.adviser,
                           status=PipelineStatus.IN_REVIEW, keywords=["mangrove"])
        RecordOwner.objects.create(record=cls.paper, user=cls.coowner)
        Author.objects.create(record=cls.paper, name="Me Person")

    def setUp(self):
        cache.clear()
        self.client.force_authenticate(self.me)

    def export(self):
        response = self.client.get(URL)
        self.assertEqual(response.status_code, 200)
        return response.json()

    # -- what it holds ------------------------------------------------------

    def test_account_details(self):
        RoleRequest.objects.create(user=self.me, requested_role=self.me.role)
        account = self.export()["account"]
        self.assertEqual(account["email"], "me@cit.edu")
        self.assertEqual(account["first_name"], "Me")
        self.assertEqual(account["role"], RoleName.STUDENT)
        self.assertTrue(account["signup_consent_given"])
        self.assertEqual(len(account["role_requests"]), 1)

    def test_their_own_account_deletion_requests(self):
        AccountDeletionRequest.objects.create(user=self.me, status=RequestStatus.DECLINED, reason="You still advise a paper.")
        requests = self.export()["account"]["deletion_requests"]
        self.assertEqual([(r["status"], r["reason"]) for r in requests], [(RequestStatus.DECLINED, "You still advise a paper.")])
        self.assertNotIn("decided_by", requests[0])

    def test_the_details_of_a_paper_they_own(self):
        papers = self.export()["papers_owned"]
        self.assertEqual([p["id"] for p in papers], [self.paper.pk])
        paper = papers[0]
        self.assertEqual(paper["title"], "My thesis on mangroves")
        self.assertEqual(paper["keywords"], ["mangrove"])
        self.assertEqual(paper["pipeline_status"], PipelineStatus.IN_REVIEW)
        self.assertEqual([a["name"] for a in paper["authors"]], ["Me Person"])
        self.assertTrue(paper["you_are_primary_owner"])

    def test_a_deleted_paper_stays_in_and_is_flagged(self):
        gone = _paper("Deleted draft", self.me)
        gone.is_deleted = True
        gone.save(update_fields=["is_deleted"])
        papers = {p["id"]: p for p in self.export()["papers_owned"]}
        self.assertTrue(papers[gone.pk]["is_deleted"])

    def test_saved_papers_and_reading_status(self):
        published = _paper("Public work", self.stranger, status=PipelineStatus.PUBLISHED)
        SavedRecord.objects.create(owner=self.me, record=published, reading_status=ReadingStatus.READING)
        saved = self.export()["saved_papers"]
        self.assertEqual(len(saved), 1)
        self.assertEqual(saved[0]["record_id"], published.pk)
        self.assertEqual(saved[0]["title"], "Public work")
        self.assertEqual(saved[0]["reading_status"], ReadingStatus.READING)

    def test_the_optional_profile_is_in_the_account_section(self):
        from apps.accounts import profile

        self.me.bio = "I study mangroves."
        self.me.save(update_fields=["bio"])
        profile.set_interests(self.me, ["Ecology", "Remote sensing"])
        account = self.export()["account"]
        self.assertEqual(account["bio"], "I study mangroves.")
        self.assertEqual(account["research_interests"], ["Ecology", "Remote sensing"])
        self.assertFalse(account["has_photo"])

    def test_saved_feeds_are_the_persons_own(self):
        from apps.library.models import SavedFeed

        SavedFeed.objects.create(owner=self.me, name="Water", query={"q": "water"})
        SavedFeed.objects.create(owner=self.stranger, name="Not mine", query={"q": "x"})
        feeds = self.export()["saved_feeds"]
        self.assertEqual([(f["name"], f["query"]) for f in feeds], [("Water", {"q": "water"})])

    def test_saved_replies_are_the_persons_own(self):
        from apps.reviews.models import SavedReply

        SavedReply.objects.create(owner=self.me, title="Typo", body="There's a typo here.")
        SavedReply.objects.create(owner=self.stranger, title="Not mine", body="x")
        replies = self.export()["saved_replies"]
        self.assertEqual([(r["title"], r["body"]) for r in replies], [("Typo", "There's a typo here.")])

    def test_viewed_marks_are_the_persons_own(self):
        from apps.records.models import RecordVersion, ReviewText
        from apps.reviews.models import ViewedMark

        paper = _paper("Compared", self.stranger, status=PipelineStatus.PUBLISHED)
        version = RecordVersion.objects.create(record=paper, number=1)
        reading = ReviewText.objects.create(record=paper, source_file="x.pdf")
        for who in (self.me, self.stranger):
            ViewedMark.objects.create(user=who, record=paper, version=version, reading=reading,
                                      section_key="methods", text_hash="a" * 64)
        marks = self.export()["viewed_marks"]
        self.assertEqual([(m["record_id"], m["version"], m["section"]) for m in marks],
                         [(paper.pk, 1, "methods")])

    def test_a_finished_review_round_is_in_the_acts_of_its_actor_only(self):
        from apps.reviews.models import ReviewRound

        paper = _paper("Reviewed", self.stranger, status=PipelineStatus.PUBLISHED)
        ReviewRound.objects.create(
            record=paper, actor=self.me, party=Party.ADVISER, verdict=ReviewVerdict.COMMENT_ONLY, summary="Looks fine.",
        )
        mine = self.export()["workflow_acts"]["review_rounds"]
        self.assertEqual([r["summary"] for r in mine], ["Looks fine."])
        self.client.force_authenticate(self.stranger)
        theirs = self.client.get(URL).json()["workflow_acts"]["review_rounds"]
        self.assertEqual(theirs, [])

    def test_a_saved_paper_they_can_no_longer_read_is_listed_without_its_title(self):
        hidden = _paper("Someone's draft", self.stranger)
        SavedRecord.objects.create(owner=self.me, record=hidden)
        saved = self.export()["saved_papers"][0]
        self.assertEqual(saved["record_id"], hidden.pk)
        self.assertIsNone(saved["title"])
        self.assertFalse(saved["available"])
        self.assertNotIn("Someone's draft", _text(self.client.get(URL)))

    def test_discovery_dismissals(self):
        published = _paper("Not for me", self.stranger, status=PipelineStatus.PUBLISHED)
        DiscoveryDismissal.objects.create(user=self.me, record=published)
        self.assertEqual(self.export()["discovery"]["not_interested"][0]["record_id"], published.pk)

    def test_download_and_delete_requests(self):
        published = _paper("Requested", self.stranger, status=PipelineStatus.PUBLISHED)
        DownloadRequest.objects.create(
            record=published, requested_by=self.me, note="for my literature review",
            status=RequestStatus.DECLINED, reviewed_by=self.stranger, rdco_note="Embargoed.",
        )
        DeleteRequest.objects.create(record=self.paper, requested_by=self.me, reason="Wrong file")
        body = self.export()
        download = body["download_requests"][0]
        self.assertEqual(download["your_note"], "for my literature review")
        self.assertEqual(download["office_note"], "Embargoed.")
        self.assertEqual(download["status"], RequestStatus.DECLINED)
        self.assertEqual(body["delete_requests"][0]["reason"], "Wrong file")
        # The person who ruled on it is not named.
        self.assertNotIn("stranger@cit.edu", _text(self.client.get(URL)))

    def test_notifications_without_the_sender(self):
        kind = NotificationType.objects.get_or_create(name="note")[0]
        row = Notification.objects.create(
            sender=self.stranger, recipient=self.me, notif_type=kind, message="Your paper moved",
            record=self.paper,
        )
        NotificationRead.objects.create(notification=row, user=self.me)
        received = self.export()["notifications"]["received"]
        self.assertEqual(received[0]["message"], "Your paper moved")
        self.assertIsNotNone(received[0]["read_at"])
        self.assertNotIn("stranger@cit.edu", _text(self.client.get(URL)))

    def test_what_they_wrote_as_a_reviewer(self):
        published = _paper("Reviewed work", self.stranger, status=PipelineStatus.PUBLISHED)
        Review.objects.create(record=published, reviewed_by=self.me, stage="adviser",
                              status="approved", comment="Looks sound.")
        ReviewComment.objects.create(record=published, author=self.me, body="One question on chapter 2.",
                                     suggestion="forty-two respondents")
        acts = self.export()["workflow_acts"]
        self.assertEqual(acts["reviews"][0]["comment"], "Looks sound.")
        self.assertEqual(acts["review_comments"][0]["body"], "One question on chapter 2.")
        # Suggested wording is the reviewer's own writing too (IR-876).
        self.assertEqual(acts["review_comments"][0]["suggestion"], "forty-two respondents")

    def test_consent_history_is_every_notice_answer_the_person_gave(self):
        from apps.accounts.models import DataNotice
        from apps.accounts.notice import answer_notice

        number = DataNotice.current().number
        answer_notice(self.me, notice_version=number, ai_consent=False)
        answer_notice(self.me, notice_version=number, ai_consent=True)
        answer_notice(self.stranger, notice_version=number, ai_consent=True)
        consent = self.export()["consent"]
        self.assertTrue(consent["signup_consent_given"])
        self.assertEqual(consent["answered_notice_version"], number)
        self.assertIs(consent["ai_consent"], True)
        self.assertEqual(
            [(h["notice_version"], h["ai_consent"], h["agreed_data_privacy_agreement"]) for h in consent["history"]],
            [(number, False, True), (number, True, True)],
        )

    def test_a_paper_consent_stamp_the_person_gave(self):
        from django.utils import timezone

        self.paper.dpa_accepted_at = timezone.now()
        self.paper.dpa_accepted_by = self.me
        self.paper.save(update_fields=["dpa_accepted_at", "dpa_accepted_by"])
        self.assertEqual(self.export()["consent"]["paper_consents"][0]["record_id"], self.paper.pk)

    # -- what it leaves out -------------------------------------------------

    def test_other_owners_and_the_adviser_are_counted_never_named(self):
        paper = self.export()["papers_owned"][0]
        self.assertEqual(paper["other_owner_count"], 1)
        self.assertTrue(paper["has_adviser"])
        self.assertFalse(paper["you_are_adviser"])
        text = _text(self.client.get(URL))
        for gone in ("coowner@cit.edu", "Coowner", "adviser@cit.edu", "Adviser Person"):
            with self.subTest(gone=gone):
                self.assertNotIn(gone, text)
        self.assertNotIn(f'"id": {self.coowner.pk},', json.dumps(self.client.get(URL).json(), indent=1))

    def test_other_peoples_review_comments_and_notes_are_left_out(self):
        Review.objects.create(record=self.paper, reviewed_by=self.adviser, stage="adviser",
                              status="declined", comment="PRIVATE reviewer note")
        ReviewComment.objects.create(record=self.paper, author=self.adviser, body="ADVISER comment on my thesis")
        ReviewComment.objects.create(record=self.paper, author=self.coowner, body="CO-OWNER comment")
        body = self.export()
        text = json.dumps(body)
        for gone in ("PRIVATE reviewer note", "ADVISER comment", "CO-OWNER comment"):
            with self.subTest(gone=gone):
                self.assertNotIn(gone, text)
        self.assertEqual(body["workflow_acts"]["reviews"], [])
        self.assertEqual(body["workflow_acts"]["review_comments"], [])

    def test_a_paper_they_only_advise_is_not_in_the_papers_they_own(self):
        advised = _paper("Advised, not owned", self.stranger, adviser=self.me, status=PipelineStatus.IN_REVIEW)
        ids = [p["id"] for p in self.export()["papers_owned"]]
        self.assertNotIn(advised.pk, ids)

    def test_nobody_elses_conversation_or_library_is_in_it(self):
        published = _paper("Public work", self.stranger, status=PipelineStatus.PUBLISHED)
        theirs = Conversation.objects.create(user=self.stranger, title="THEIR CHAT")
        Turn.objects.create(conversation=theirs, question="THEIR QUESTION", answer="THEIR ANSWER", state="generated")
        SavedRecord.objects.create(owner=self.stranger, record=published)
        body = self.export()
        self.assertNotIn("THEIR", json.dumps(body))
        self.assertEqual(body["saved_papers"], [])

    def test_no_credential_is_in_it(self):
        text = _text(self.client.get(URL))
        self.assertNotIn(User.objects.get(pk=self.me.pk).password, text)
        self.assertNotIn("pbkdf2", text)

        def keys(node):
            if isinstance(node, dict):
                for key, value in node.items():
                    yield key
                    yield from keys(value)
            elif isinstance(node, list):
                for item in node:
                    yield from keys(item)

        forbidden = {"password", "token", "grant_token", "jti", "credential_version", "secret", "key_hash"}
        found = {key for key in keys(self.export()) if key in forbidden or "token" in key or "password" in key}
        self.assertEqual(found, set())


class ConversationRuleTests(APITestCase):
    """A Turn citing a paper the person can't read now stays out (the reopening rule)."""

    @classmethod
    def setUpTestData(cls):
        cls.me = _user("reader@cit.edu")
        cls.author = _user("author@cit.edu")
        cls.open_paper = _paper("Still public", cls.author, status=PipelineStatus.PUBLISHED)
        cls.pulled_paper = _paper("Soon pulled", cls.author, status=PipelineStatus.PUBLISHED)
        cls.conversation = Conversation.objects.create(user=cls.me, title="Mangroves")
        cls.keeps = cls._turn("What is public?", "A public answer [1].", cls.open_paper)
        cls.pulled = cls._turn("What was pulled?", "SECRET answer from the pulled paper [1].", cls.pulled_paper)
        cls.uncited = Turn.objects.create(
            conversation=cls.conversation, question="Hello?", answer="Hi.", state="generated",
        )

    @classmethod
    def _turn(cls, question, answer, record):
        turn = Turn.objects.create(
            conversation=cls.conversation, question=question, answer=answer, state="generated",
        )
        TurnCitation.objects.create(turn=turn, marker=1, record=record, page=3)
        return turn

    def setUp(self):
        cache.clear()
        self.client.force_authenticate(self.me)

    def turns(self):
        body = self.client.get(URL).json()
        self.assertEqual(len(body["conversations"]), 1)
        return body["conversations"][0]

    def test_every_turn_stays_while_its_papers_are_readable(self):
        conversation = self.turns()
        self.assertEqual([t["id"] for t in conversation["turns"]],
                         [self.keeps.pk, self.pulled.pk, self.uncited.pk])
        self.assertEqual(conversation["turns_left_out"], 0)
        self.assertEqual(conversation["turns"][0]["citations"][0]["title"], "Still public")
        self.assertEqual(conversation["turns"][0]["citations"][0]["page"], 3)

    def test_a_turn_citing_a_paper_now_unreadable_stays_out_whole(self):
        self.pulled_paper.pipeline_status = PipelineStatus.DRAFT
        self.pulled_paper.save(update_fields=["pipeline_status"])
        response = self.client.get(URL)
        conversation = response.json()["conversations"][0]
        self.assertEqual([t["id"] for t in conversation["turns"]], [self.keeps.pk, self.uncited.pk])
        self.assertEqual(conversation["turns_left_out"], 1)
        text = _text(response)
        for gone in ("SECRET answer", "What was pulled?", "Soon pulled"):
            with self.subTest(gone=gone):
                self.assertNotIn(gone, text)

    def test_a_paper_deleted_since_leaves_its_turns_out_too(self):
        self.pulled_paper.is_deleted = True
        self.pulled_paper.save(update_fields=["is_deleted"])
        self.assertEqual(self.turns()["turns_left_out"], 1)

    def test_the_rule_is_the_one_a_reopened_conversation_uses(self):
        from apps.ai.history import readable_record_ids

        self.pulled_paper.pipeline_status = PipelineStatus.DRAFT
        self.pulled_paper.save(update_fields=["pipeline_status"])
        readable = readable_record_ids(self.me, {self.open_paper.pk, self.pulled_paper.pk})
        self.assertEqual(readable, {self.open_paper.pk})

    def test_a_paper_chat_about_an_unreadable_paper_has_no_title(self):
        hidden = _paper("A private draft", self.author)
        Conversation.objects.create(user=self.me, title="About it", record=hidden)
        body = self.client.get(URL).json()
        about = [c["about_paper"] for c in body["conversations"] if c["about_paper"]][0]
        self.assertEqual(about["record_id"], hidden.pk)
        self.assertIsNone(about["title"])
        self.assertNotIn("A private draft", json.dumps(body))
