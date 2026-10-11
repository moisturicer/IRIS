"""
IR-418: Record detail's `capabilities` against the endpoints that own them.

ADR-032 §10 and §12: the list is a rendering hint and the server stays
authoritative, so "for each role × state" it must match the action endpoints'
own refusals -- one table-driven test, so the hint cannot drift from the
authority. This is that test.

Every row is a record state and a viewer. For each row it checks:

1. the exact set of capabilities Record detail offers that viewer;
2. **offered => not refused for who you are.** Each capability's own endpoint,
   called for real, answers anything but 403 or 404. A blocked action may
   still be offered so its reason can be shown, so a 400 or 409 is allowed;
3. **not offered => the endpoint would not carry it out.** The same call
   answers anything but 2xx.

Every probe runs inside a savepoint that is rolled back, so no probe changes
the state the next one sees. `cite` and `replace_manuscript` have no endpoint
of their own (`replace_manuscript` rides on the owner's record update and is
offered exactly with `create_version`), so they are checked by set only. The
three delete keys share `DELETE /records/<id>/` (IR-508), so each is probed only
in the statuses whose act it names.

**No capability is waived.** The record update and `submit/` were wider than
any offer until IR-507 narrowed them to owners, and an owner's edit to where
`edit_details` is offered; rule 3 was waived for those two until then.
"""

import shutil
import tempfile

from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import transaction
from django.test import override_settings
from django.urls import reverse

from apps.reviews.models import RecordAssignment, ReviewerSeat
from apps.reviews.test_decisions import DecisionTestBase
from core.enums import AssignmentState, Party, RecordTypeName, ResubmissionRequestState, SeatState
from core.permissions import DELETE_CAPABILITY

# Keys ADR-032 names that no endpoint serves yet, plus `decide`, the legacy
# decision form IR-260 removed. The server must never offer one.
UNBUILT = {"continue_as", "set_visibility", "comment_review", "comment_public", "decide"}


def _rolled_back(call):
    """`call()`'s response, with everything it wrote undone."""
    with transaction.atomic():
        response = call()
        transaction.set_rollback(True)
    return response


class CapabilitiesMatchTheEndpoints(DecisionTestBase):
    """ADR-032 §12: `capabilities` for each role × state matches the endpoints."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # An attached file is written to disk; never into the checkout's media.
        cls._media_root = tempfile.mkdtemp(prefix="iris-test-media-")
        cls._media_override = override_settings(MEDIA_ROOT=cls._media_root)
        cls._media_override.enable()

    @classmethod
    def tearDownClass(cls):
        cls._media_override.disable()
        shutil.rmtree(cls._media_root, ignore_errors=True)
        super().tearDownClass()

    # --- the states ------------------------------------------------------------------

    def draft(self):
        return self.make_record()

    def with_adviser_unopened(self):
        return self.new_model()

    def with_adviser_open(self):
        return self.at_adviser()

    def itso_pool(self):
        return self.routed(Party.ITSO)

    def itso_open(self):
        record = self.routed(Party.ITSO)
        self.opened_seat(record, Party.ITSO, self.itso)
        return record

    def revision_asked_by_itso(self):
        record = self.itso_open()
        self.asked(record, self.itso)
        return record

    def rdco_open(self):
        return self.at_rdco()

    def published(self):
        record = self.at_adviser()
        self.decided(record, self.adviser, "publish")
        return record

    def proposal_with_adviser(self):
        return self.at_adviser(RecordTypeName.PROPOSAL)

    # --- the probes: one real call per capability -------------------------------------

    def _call(self, user, method, url, body=None, fmt="json"):
        self.client.force_authenticate(user)
        return _rolled_back(lambda: getattr(self.client, method)(url, body or {}, format=fmt))

    def _decide(self, outcome):
        def probe(record, user, detail):
            token = ((detail or {}).get("decision") or {}).get("token") or "none"
            return self._call(user, "post", reverse("record-decide", args=[record.pk]), {
                "outcome": outcome, "comment": "Reason for the decision.", "token": token,
            })
        return probe

    def _probes(self):
        def url(name, record, *extra):
            return reverse(name, args=[record.pk, *extra])

        def attach(record, user, detail):
            pdf = SimpleUploadedFile("note.pdf", b"%PDF-1.4\n%%EOF\n", content_type="application/pdf")
            return self._call(
                user, "post", reverse("record-file-upload"),
                {"record": record.pk, "file": pdf}, fmt="multipart",
            )

        def withdraw(record, user, detail):
            mine = ((detail or {}).get("revision") or {}).get("withdrawable")
            open_ids = [r.pk for r in record.resubmission_requests.filter(state=ResubmissionRequestState.OPEN)]
            request_id = mine or (open_ids[0] if open_ids else None)
            if request_id is None:
                return None
            return self._call(user, "post", url("record-withdraw-revision-request", record, request_id))

        def add_reviewer(record, user, detail):
            assignments = RecordAssignment.objects.filter(
                record=record, state=AssignmentState.ACTIVE,
            ).exclude(party=Party.ADVISER)
            responses = [
                self._call(user, "get", reverse("assignment-add-reviewer", args=[a.pk]))
                for a in assignments
            ]
            ok = [r for r in responses if r.status_code < 300]
            return (ok or responses or [None])[0]

        def delete_as(act):
            # The three delete keys share `DELETE /records/<id>/`, which does
            # the act of the record's status (IR-508). A key is probed only in
            # the statuses whose act it names; elsewhere it is not this key's
            # call, and the key that does name it is probed instead.
            def probe(record, user, detail):
                if DELETE_CAPABILITY.get(record.pipeline_status) != act:
                    return None
                return self._call(user, "delete", url("record-detail", record))
            return probe

        def open_review(record, user, detail):
            seat = ReviewerSeat.objects.filter(
                assignment__record=record, reviewer=user, state=SeatState.ASSIGNED,
            ).first()
            if seat is None:
                return None
            return self._call(user, "post", reverse("seat-open", args=[seat.pk]))

        return {
            "tag_ip": lambda r, u, d: self._call(u, "patch", url("record-tags", r), {"ip_type": "patent"}),
            "attach_file": attach,
            "accept_route": lambda r, u, d: self._call(u, "post", url("record-accept-and-route", r), {
                "to": [{"party": Party.IERC}], "reason": "Ethics review.",
            }),
            "route": lambda r, u, d: self._call(u, "post", url("record-route", r), {
                "to": [{"party": Party.KTTO}], "reason": "Commercial potential.",
            }),
            "office_review": lambda r, u, d: self._call(
                u, "post", url("record-office-review", r), {"outcome": "cleared", "comment": ""},
            ),
            "request_revision": lambda r, u, d: self._call(
                u, "post", url("record-request-revision", r), {"reason": "Please revise."},
            ),
            "withdraw_revision": withdraw,
            "request_document": lambda r, u, d: self._call(
                u, "post", url("record-document-requests", r),
                {"message": "Please attach it.", "items": [{"label": "Consent form"}]},
            ),
            "accept_publish": self._decide("publish"),
            "keep_unlisted": self._decide("keep_unlisted"),
            "reject": self._decide("reject"),
            "accept_proposal": self._decide("accept"),
            "add_reviewer": add_reviewer,
            "edit_details": lambda r, u, d: self._call(
                u, "patch", url("record-detail", r), {"title": "An edited title"},
            ),
            # With consent given, so a 400 is a refusal, not a missing tick.
            "continue_draft": lambda r, u, d: self._call(
                u, "post", url("record-submit", r), {"dpa_accepted": True},
            ),
            "create_version": lambda r, u, d: self._call(u, "post", url("record-new-version", r)),
            "open_review": open_review,
            "delete_record": delete_as("delete_record"),
            "withdraw_submission": delete_as("withdraw_submission"),
            "request_deletion": delete_as("request_deletion"),
        }

    # --- the table ---------------------------------------------------------------------

    def viewers(self):
        return {
            "owner": self.owner, "adviser": self.adviser, "itso": self.itso,
            "ierc": self.ierc, "rdco": self.rdco, "stranger": self.stranger,
        }

    # (state, viewer) -> the exact offer, or None where the record is a 404.
    # Office staff are offered `tag_ip` on every record they can see (decided
    # 2026-10-11: the offer follows `tags/`, not published records alone).
    OFFICE = {"cite", "tag_ip"}
    ADVISER_AT_ENTRY = {
        "cite", "open_review", "accept_route", "accept_publish", "reject",
        "request_document", "request_revision",
    }
    ITSO_SEATED = {
        "cite", "tag_ip", "attach_file", "request_document", "open_review",
        "office_review", "add_reviewer", "route",
    }
    # An owner is offered the one delete its record's status names (IR-508).
    OWNER_IN_REVIEW = {"cite", "withdraw_submission"}
    EXPECTED = {
        "draft": {
            "owner": {"cite", "continue_draft", "edit_details", "delete_record"}, "adviser": {"cite"},
            "itso": OFFICE, "ierc": OFFICE, "rdco": OFFICE, "stranger": None,
        },
        "with_adviser_unopened": {
            "owner": OWNER_IN_REVIEW, "adviser": ADVISER_AT_ENTRY,
            "itso": OFFICE, "ierc": OFFICE, "rdco": OFFICE, "stranger": None,
        },
        "with_adviser_open": {
            "owner": OWNER_IN_REVIEW, "adviser": ADVISER_AT_ENTRY,
            "itso": OFFICE, "ierc": OFFICE, "rdco": OFFICE, "stranger": None,
        },
        # ITSO's pool: any ITSO member may file and ask for documents, but
        # opens, clears and routes only once seated.
        "itso_pool": {
            "owner": OWNER_IN_REVIEW, "adviser": {"cite"},
            "itso": {"cite", "tag_ip", "attach_file", "request_document"},
            "ierc": OFFICE, "rdco": OFFICE, "stranger": None,
        },
        "itso_open": {
            "owner": OWNER_IN_REVIEW, "adviser": {"cite"}, "itso": ITSO_SEATED | {"request_revision"},
            "ierc": OFFICE, "rdco": OFFICE, "stranger": None,
        },
        # ITSO asked once, so it is offered the withdrawal, not a second ask.
        "revision_asked_by_itso": {
            "owner": OWNER_IN_REVIEW | {"create_version", "replace_manuscript", "edit_details"},
            "adviser": {"cite"}, "itso": ITSO_SEATED | {"withdraw_revision"},
            "ierc": OFFICE, "rdco": OFFICE, "stranger": None,
        },
        # RDCO decides, and -- seated on an office party -- may add a colleague.
        "rdco_open": {
            "owner": OWNER_IN_REVIEW, "adviser": {"cite"}, "itso": OFFICE, "ierc": OFFICE,
            "rdco": {
                "cite", "tag_ip", "attach_file", "request_document", "open_review",
                "add_reviewer", "route", "request_revision",
                "accept_publish", "keep_unlisted", "reject",
            },
            "stranger": None,
        },
        "published": {
            "owner": {"cite", "request_deletion"}, "adviser": {"cite"},
            "itso": OFFICE, "ierc": OFFICE, "rdco": OFFICE, "stranger": {"cite"},
        },
        # A Proposal's Adviser accepts it or rejects it; it is never routed.
        "proposal_with_adviser": {
            "owner": OWNER_IN_REVIEW,
            "adviser": {
                "cite", "open_review", "accept_proposal", "reject",
                "request_document", "request_revision",
            },
            "itso": OFFICE, "ierc": OFFICE, "rdco": OFFICE, "stranger": None,
        },
    }

    def _offer(self, record, user):
        self.client.force_authenticate(user)
        response = self.client.get(reverse("record-detail", args=[record.pk]))
        return response.status_code, (response.data if response.status_code == 200 else None)

    def test_each_role_and_state_matches_the_endpoints(self):
        probes = self._probes()
        for state, row in self.EXPECTED.items():
            record = getattr(self, state)()
            for name, user in self.viewers().items():
                with self.subTest(state=state, viewer=name):
                    code, detail = self._offer(record, user)
                    expected = row[name]
                    if expected is None:
                        self.assertEqual(code, 404)
                        offered = set()
                    else:
                        self.assertEqual(code, 200)
                        offered = set(detail["capabilities"])
                        self.assertEqual(offered, expected)
                        self.assertFalse(offered & UNBUILT)
                    for capability, probe in probes.items():
                        response = probe(record, user, detail)
                        if response is None:
                            continue
                        got = (capability, response.status_code)
                        if capability in offered:
                            self.assertNotIn(response.status_code, (403, 404), got)
                        else:
                            self.assertGreaterEqual(response.status_code, 300, got)

    def test_edit_and_submit_refuse_what_is_not_offered(self):
        """
        IR-507: the record update and `submit/` were `IsOwnerOrStaff`, so office
        staff edited and submitted records that were not theirs, and owners
        edited in every state. Pinned here as a strict xfail until the
        endpoints were narrowed; the table above now holds them to rule 3 as
        well, and this stays as the named regression.
        """
        probes = self._probes()
        for state in ("draft", "itso_open", "published"):
            record = getattr(self, state)()
            for name, user in self.viewers().items():
                _, detail = self._offer(record, user)
                offered = set(detail["capabilities"]) if detail else set()
                for capability in sorted({"edit_details", "continue_draft"} - offered):
                    status_code = probes[capability](record, user, detail).status_code
                    assert status_code >= 300, (state, name, capability, status_code)
