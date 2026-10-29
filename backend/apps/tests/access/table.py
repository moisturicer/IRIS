"""
The declared expected-access table (IR-615).

Keyed by app, then URL name, then HTTP method. Every route
`routes.enumerate_routes()` finds must appear here, or in a namespace
`routes.OUT_OF_SCOPE_NAMESPACES` names; anything
else fails `test_access_matrix` with the route's name.

**Never edit a row to make a failing route pass** (IR-611). A row says what
the route should do, from the ADRs and from the decisions written into the
code it governs. A route that does otherwise is a bug, filed with the
`area-security` label and marked `KnownDefect` in its cell, which keeps the
correct outcome and fails the day the bug is fixed.

Each row lists one outcome per role, in `world.ROLES` order:

    anon  other  owner  adviser  seated  unseated  coordinator  rdco  admin

`anon` has no credentials; `other` is a Student with no claim on anything;
`owner` owns every record in the world; `adviser` advises them; `seated`
holds an opened ITSO seat on `record` and `revising`; `unseated` is an ITSO
pool member and `coordinator` an ITSO coordinator, neither seated; `rdco` is
RDCO, seated nowhere; `admin` is the role-less superuser. Each role's
relation to an object is the world's (see `world.build_world`), so on
`at_adviser`, which no office holds yet, `seated` is one more ITSO member.
"""

from __future__ import annotations

from dataclasses import dataclass

from .cells import (
    ANON, DENY, DOWNLOAD_TOKEN, HIDE, OK, STUB, Call, Case, Ref, Upload, row,
)

# -- shorthands -------------------------------------------------------------

#: Any signed-in account; the anonymous caller is refused before lookup.
SIGNED_IN = row(ANON, OK, OK, OK, OK, OK, OK, OK, OK)
#: RDCO alone: `IsAdmin` / `IsRDCO`, a role gate before any lookup.
RDCO_ONLY = row(ANON, DENY, DENY, DENY, DENY, DENY, DENY, OK, DENY)
#: Office staff alone (`IsStaff`): KTTO, RDCO, ITSO, IERC.
OFFICE_ONLY = row(ANON, DENY, DENY, DENY, OK, OK, OK, OK, DENY)
#: `record` read through `visible_to()`: owner, Adviser, every office.
READS_RECORD = row(ANON, HIDE, OK, OK, OK, OK, OK, OK, HIDE)
#: `record`, an owner's act: visible non-owners are refused, others hidden.
OWNER_ACTS = row(ANON, HIDE, OK, DENY, DENY, DENY, DENY, DENY, HIDE)
#: `record`, the seated ITSO reviewer's act alone.
SEAT_ACTS = row(ANON, HIDE, DENY, DENY, OK, DENY, DENY, DENY, HIDE)
#: `record`'s documents: owner or office staff (`owns_or_staffs_record`, IR-153).
DOCUMENTS = row(ANON, DENY, OK, DENY, OK, OK, OK, OK, DENY)

#: ADR-022 Â§Amendment 4 point 4, recorded 2026-09-24: `authorize_record_documents`
#: answers 403 even to a caller who cannot see the Record, because the Record id
#: is the caller's own parameter. The documents app's upload and listing routes
#: only; every other route follows the 404 convention.
DOCUMENTS_EXCEPTION = (
    "ADR-022 Â§Amendment 4 point 4: authorize_record_documents answers 403 to a caller "
    "who cannot see the Record, whose id they supplied (IR-153)"
)


@dataclass(frozen=True)
class Entry:
    """A route's declared access: one or more cases per method."""

    methods: dict[str, Case | list[Case]]
    #: Cited reason this route may answer a hidden object unlike a missing one.
    waiver: str = ""

    def cases(self, method: str) -> list[Case]:
        declared = self.methods[method]
        return declared if isinstance(declared, list) else [declared]


@dataclass(frozen=True)
class Shadowed:
    """A route no request can reach: an earlier pattern matches its path first."""

    by: str
    why: str


def _case(cells, **call) -> Case:
    return Case(Call(**call), cells)


RECORD = {"pk": Ref("record")}
ROUTE_TO_IERC = {"to": [{"party": "ierc"}], "reason": "Human participants."}

RECORDS: dict[str, Entry | Shadowed] = {
    # -- the catalogue and the reader's own lists ------------------------
    "record-list": Entry({
        "GET": _case(SIGNED_IN),
        # Authors only: Student or Adviser (IR-165, AUTHOR_ROLES).
        "POST": _case(
            row(ANON, OK, OK, OK, DENY, DENY, DENY, DENY, DENY),
            data={"title": "A disclosure", "abstract": "x"},
        ),
    }),
    "api-root": Shadowed(
        by="record-list",
        why="RecordViewSet is registered at the router's empty prefix, so its list "
            "matches /records/ before DefaultRouter's root view",
    ),
    "record-facets": Entry({"GET": _case(SIGNED_IN)}),
    "record-for-you": Entry({"GET": _case(SIGNED_IN)}),
    "record-interests": Entry({
        "GET": _case(SIGNED_IN),
        "PUT": _case(SIGNED_IN, data={}),
        "DELETE": _case(SIGNED_IN),
    }),
    # IR-576: dismiss only a readable Record; Undo deletes only one's own
    # feedback and returns the same empty success for hidden or missing ids.
    "record-not-interested": Entry({
        "POST": _case(READS_RECORD, kwargs=RECORD, data={}),
        "DELETE": _case(SIGNED_IN, kwargs=RECORD),
    }),
    "record-mine": Entry({"GET": _case(SIGNED_IN)}),

    # -- one record ------------------------------------------------------
    "record-detail": Entry({
        "GET": _case(READS_RECORD, kwargs=RECORD),
        # Details, submission and deletion are an owner's alone (IR-507, IR-508).
        "PUT": _case(OWNER_ACTS, kwargs=RECORD, data={"title": "Renamed"}),
        "PATCH": _case(OWNER_ACTS, kwargs=RECORD, data={"title": "Renamed"}),
        "DELETE": _case(OWNER_ACTS, kwargs=RECORD),
    }),
    "record-submit": Entry({"POST": _case(OWNER_ACTS, kwargs=RECORD, data={})}),
    "record-manuscript": Entry({"GET": _case(READS_RECORD, kwargs=RECORD)}),
    # Earlier versions are review material: participants, or the pool of a
    # party with an active assignment (IR-479). RDCO holds none on `record`.
    "record-version-manuscript": Entry({
        "GET": _case(
            row(ANON, HIDE, OK, OK, OK, OK, OK, HIDE, HIDE),
            kwargs={"pk": Ref("record"), "number": Ref("version", "number")},
        ),
    }),
    "record-similar": Entry({"GET": _case(READS_RECORD, kwargs=RECORD)}),
    # ADR-029: novelty results belong only to the Proposal's owner.
    "record-related-research": Entry({
        "GET": _case(row(ANON, HIDE, OK, HIDE, HIDE, HIDE, HIDE, HIDE, HIDE), kwargs=RECORD),
    }),
    "record-tracker": Entry({"GET": _case(READS_RECORD, kwargs=RECORD)}),
    "record-increment-access": Entry({"POST": _case(READS_RECORD, kwargs=RECORD, data={})}),
    # The manuscript's own text, for the person publishing it (IR-406).
    "record-metadata-suggestions": Entry({
        "GET": _case(row(ANON, HIDE, OK, HIDE, HIDE, HIDE, HIDE, HIDE, HIDE), kwargs=RECORD),
    }),
    # Any office, on any record it can see (decided 2026-10-11). A role gate
    # before lookup, so a non-office caller's 403 is the same for a missing id.
    "record-tags": Entry({"PATCH": _case(OFFICE_ONLY, kwargs=RECORD, data={"is_ip": True})}),

    # -- document requests (ADR-022 Â§5, Â§Amendment 5) --------------------
    # Read by participation, never by role: the owner, and anyone who can
    # staff a party that took part -- the Adviser, ITSO's whole pool. RDCO
    # took no part in `record`, so sees it but not its requests.
    "record-document-requests": Entry({
        "GET": _case(row(ANON, HIDE, OK, OK, OK, OK, OK, DENY, HIDE), kwargs=RECORD),
        # Asked by an active assignment the caller can staff: ITSO's, here.
        "POST": _case(
            row(ANON, HIDE, DENY, DENY, OK, OK, OK, DENY, HIDE), kwargs=RECORD,
            data={"message": "Please attach it.", "items": [{"label": "Endorsement"}]},
        ),
    }),
    "record-document-request-slots": Entry({"GET": _case(READS_RECORD, kwargs=RECORD)}),

    # -- the review acts (ADR-032) -----------------------------------------
    # At the Adviser's step: only the record's Adviser accepts and routes, or decides.
    "record-accept-and-route": Entry({
        "POST": _case(
            row(ANON, HIDE, DENY, OK, DENY, DENY, DENY, DENY, HIDE),
            kwargs={"pk": Ref("at_adviser")},
            data={"to": [{"party": "itso"}], "reason": "Possible IP."},
        ),
    }),
    "record-decide": Entry({
        "POST": _case(
            row(ANON, HIDE, DENY, OK, DENY, DENY, DENY, DENY, HIDE),
            kwargs={"pk": Ref("at_adviser")},
            data={"outcome": "reject", "comment": "Out of scope.", "token": "stale"},
        ),
    }),
    # Past it: an office seat holder routes onward, clears, or asks for a revision.
    "record-route": Entry({"POST": _case(SEAT_ACTS, kwargs=RECORD, data=ROUTE_TO_IERC)}),
    "record-route-options": Entry({"GET": _case(SEAT_ACTS, kwargs=RECORD)}),
    "record-office-review": Entry({
        "POST": _case(SEAT_ACTS, kwargs=RECORD, data={"outcome": "cleared", "comment": ""}),
    }),
    "record-request-revision": Entry({
        "POST": _case(SEAT_ACTS, kwargs=RECORD, data={"reason": "Cite the prior art."}),
    }),
    # On `revising`, which ITSO's seat holder asked to be revised.
    "record-withdraw-revision-request": Entry({
        "POST": _case(
            SEAT_ACTS, data={},
            kwargs={"pk": Ref("revising"), "request_id": Ref("revision_request")},
        ),
    }),
    "record-new-version": Entry({
        "POST": _case(OWNER_ACTS, kwargs={"pk": Ref("revising")}, data={}),
    }),

    # -- bulk import: staff file on others' behalf --------------------------
    "record-import-excel": Entry({"POST": _case(OFFICE_ONLY, data={}, format="multipart")}),
    "record-download-template": Entry({"GET": _case(OFFICE_ONLY)}),

    # -- download requests ------------------------------------------------
    "download-requests": Entry({
        "GET": _case(RDCO_ONLY),
        "POST": _case(SIGNED_IN, data={"record": Ref("published")}),
    }),
    "download-request-detail": Entry({
        "GET": _case(RDCO_ONLY, kwargs={"pk": Ref("download_request")}),
        "PATCH": _case(
            RDCO_ONLY, kwargs={"pk": Ref("download_request")}, data={"action": "decline"},
        ),
    }),
    "download-request-approve": Entry({
        "POST": _case(RDCO_ONLY, kwargs={"pk": Ref("download_request")}, data={}),
    }),
    "download-request-decline": Entry({
        "POST": _case(RDCO_ONLY, kwargs={"pk": Ref("download_request")}, data={}),
    }),
    # The token is the credential: no account is needed, and none is enough.
    "download-redeem": Entry({
        "GET": [
            Case(Call(query={"token": DOWNLOAD_TOKEN}), row(OK, OK, OK, OK, OK, OK, OK, OK, OK),
                 label="an approved request's token"),
            Case(Call(query={"token": "forged"}),
                 row(DENY, DENY, DENY, DENY, DENY, DENY, DENY, DENY, DENY),
                 label="a forged token"),
        ],
    }),

    # -- delete requests: raised by DELETE /records/<id>/, decided by RDCO ---
    "delete-requests": Entry({"GET": _case(RDCO_ONLY)}),
    "delete-request-detail": Entry({"GET": _case(RDCO_ONLY, kwargs={"pk": Ref("delete_request")})}),
    "delete-request-approve": Entry({
        "POST": _case(RDCO_ONLY, kwargs={"pk": Ref("delete_request")}, data={}),
    }),
    "delete-request-decline": Entry({
        "POST": _case(RDCO_ONLY, kwargs={"pk": Ref("delete_request")}, data={}),
    }),

    # -- reference data and the dashboard ---------------------------------
    "classifications": Entry({"GET": _case(SIGNED_IN)}),
    "psced": Entry({"GET": _case(SIGNED_IN)}),
    "record-types": Entry({"GET": _case(SIGNED_IN)}),
    "dashboard-stats": Entry({"GET": _case(SIGNED_IN)}),
    "chart-classifications": Entry({"GET": _case(SIGNED_IN)}),
    "chart-psced": Entry({"GET": _case(SIGNED_IN)}),
}


ON_RECORD = {"record": Ref("record")}
SLOT_UPLOAD = {"record": Ref("record"), "slot": Ref("slot"), "file": Upload("new.pdf")}
UPLOAD = {"pk": Ref("upload")}
RECORD_FILE = {"pk": Ref("record_file")}

DOCUMENTS_APP: dict[str, Entry | Shadowed] = {
    "upload-slots": Entry({"GET": _case(SIGNED_IN)}),

    # -- a record's documents, named by the caller (the recorded exception) --
    "document-submit": Entry(
        {"POST": _case(DOCUMENTS, data=SLOT_UPLOAD, format="multipart")},
        waiver=DOCUMENTS_EXCEPTION,
    ),
    "record-upload-create-legacy": Entry(
        {"POST": _case(DOCUMENTS, data=SLOT_UPLOAD, format="multipart")},
        waiver=DOCUMENTS_EXCEPTION,
    ),
    "record-slot-list": Entry({"GET": _case(DOCUMENTS, kwargs={"pk": Ref("record")})},
                              waiver=DOCUMENTS_EXCEPTION),
    "record-uploads": Entry({"GET": _case(DOCUMENTS, query=ON_RECORD)}, waiver=DOCUMENTS_EXCEPTION),
    "record-files": Entry({"GET": _case(DOCUMENTS, query=ON_RECORD)}, waiver=DOCUMENTS_EXCEPTION),
    "record-files-download-all": Entry({"GET": _case(DOCUMENTS, query=ON_RECORD)},
                                       waiver=DOCUMENTS_EXCEPTION),

    # -- one upload or file, named by its own id: the 404 convention ------
    "record-upload-download": Entry({
        "GET": _case(
            row(ANON, HIDE, OK, DENY, OK, OK, OK, OK, HIDE),
            kwargs=UPLOAD,
        ),
    }),
    "record-upload-delete": Entry({
        "DELETE": _case(
            row(ANON, HIDE, OK, DENY, OK, OK, OK, OK, HIDE),
            kwargs=UPLOAD,
        ),
    }),
    "record-file-download": Entry({
        "GET": _case(
            row(ANON, HIDE, OK, DENY, OK, OK, OK, OK, HIDE),
            kwargs=RECORD_FILE,
        ),
    }),
    # The office that filed it, while it takes part (IR-476): ITSO's pool.
    "record-file-delete": Entry({
        "DELETE": _case(row(ANON, HIDE, DENY, DENY, OK, OK, OK, DENY, HIDE), kwargs=RECORD_FILE),
    }),

    # -- office acts on documents ----------------------------------------
    # An office taking part files its own supplementary file (IR-474).
    "record-file-upload": Entry(
        {"POST": _case(
            row(ANON, DENY, DENY, DENY, OK, OK, OK, DENY, DENY),
            data={"record": Ref("record"), "file": Upload("note.pdf")}, format="multipart",
        )},
        waiver=DOCUMENTS_EXCEPTION,
    ),
    "upload-reviews": Entry({
        "POST": _case(
            OFFICE_ONLY, data={"upload": Ref("upload"), "status": Ref("upload_status")},
        ),
    }),

    # -- deciding a document request (ADR-022 Â§Amendment 4) -------------
    # 404 off a visible Record; 403 to a visible reader who is not the
    # requesting party; the party, not the person: ITSO's whole pool.
    "document-request-detail": Entry({
        "PATCH": _case(
            row(ANON, HIDE, DENY, DENY, OK, OK, OK, DENY, HIDE),
            kwargs={"pk": Ref("document_request")}, data={"action": "withdraw"},
        ),
    }),
    "document-request-item-detail": Entry({
        "PATCH": _case(
            row(ANON, HIDE, DENY, DENY, OK, OK, OK, DENY, HIDE),
            kwargs={"pk": Ref("document_request_item")}, data={"action": "accept"},
        ),
    }),
}

REVIEW_DEADLINES: dict[str, Entry | Shadowed] = {
    # ADR-043 Â§6: only this office's coordinator, with the same hidden-id
    # convention as seats. The document request supplies its assignment id.
    "assignment-extend": Entry({
        "POST": _case(
            row(ANON, HIDE, DENY, DENY, DENY, DENY, OK, DENY, HIDE),
            kwargs={"pk": Ref("document_request", "assignment_id")},
            data={"due_at": "2099-12-31T23:59:00+08:00", "reason": "Committee unavailable"},
        ),
    }),
}

# IR-616: every remaining app is declared; there is no pending exemption.
PUBLIC = row(OK, OK, OK, OK, OK, OK, OK, OK, OK)
PRIVATE = row(ANON, HIDE, OK, HIDE, HIDE, HIDE, HIDE, HIDE, HIDE)
COORDINATOR = row(ANON, HIDE, DENY, DENY, DENY, DENY, OK, DENY, HIDE)
REVIEWER = row(ANON, DENY, DENY, OK, OK, OK, OK, OK, DENY)
POSTER = row(ANON, DENY, DENY, OK, DENY, DENY, DENY, OK, DENY)

ACCOUNTS = {
    "auth-register": Entry({"POST": _case(PUBLIC, data={})}),
    # Missing credentials are rejected for every caller, including signed-in users.
    "auth-login": Entry({"POST": _case(row(*([ANON]*9)), data={})}),
    "auth-logout": Entry({"POST": _case(SIGNED_IN, data={})}),
    "token-refresh": Entry({"POST": _case(PUBLIC, data={})}),
    "auth-activate": Entry({"GET": _case(PUBLIC, kwargs={"uidb64": "invalid", "token": "invalid"})}),
    "password-change": Entry({"POST": _case(SIGNED_IN, data={})}),
    "user-list": Entry({"GET": _case(RDCO_ONLY)}),
    "user-advisers": Entry({"GET": _case(SIGNED_IN)}),
    "user-me": Entry({m: _case(SIGNED_IN, **({} if m == "GET" else {"data": {"first_name": "Updated"}}))
                      for m in ("GET", "PUT", "PATCH")}),
    "user-detail": Entry({m: _case(RDCO_ONLY, kwargs={"pk": Ref("target_user")},
                                 **({} if m == "GET" else {"data": {"first_name": "Updated"}}))
                          for m in ("GET", "PUT", "PATCH")}),
    "user-change-role": Entry({"PATCH": _case(RDCO_ONLY, kwargs={"pk": Ref("target_user")}, data={"role_name": "Adviser"})}),
    "user-coordinator": Entry({"PATCH": _case(RDCO_ONLY, kwargs={"pk": Ref("target_user")}, data={"is_office_coordinator": True})}),
    "user-lock": Entry({"PATCH": _case(RDCO_ONLY, kwargs={"pk": Ref("target_user")}, data={})}),
    "user-locked": Entry({"GET": _case(RDCO_ONLY)}),
    "user-unlock": Entry({"POST": _case(RDCO_ONLY, kwargs={"pk": Ref("target_user")}, data={})}),
    "role-request-list": Entry({"GET": _case(RDCO_ONLY)}),
    "role-request-detail": Entry({"PATCH": _case(RDCO_ONLY, kwargs={"pk": Ref("role_request")}, data={"action": "approve"})}),
    "user-sessions": Entry({"GET": _case(RDCO_ONLY)}),
    "user-session-revoke": Entry({"DELETE": _case(RDCO_ONLY, kwargs={"jti": Ref("session_token", "jti")})}),
    "college-list": Entry({"GET": _case(PUBLIC)}),
    "department-list": Entry({"GET": _case(PUBLIC)}),
    "course-list": Entry({"GET": _case(PUBLIC)}),
    "system-setting": Entry({"GET": _case(SIGNED_IN, kwargs={"key": "matrix-setting"}),
                             "PATCH": _case(RDCO_ONLY, kwargs={"key": "matrix-setting"}, data={"value": "updated"})}),
}

ASSIGNMENT = {"pk": Ref("assignment")}
SEAT = {"pk": Ref("seat")}
REVIEWS = {
    **REVIEW_DEADLINES,
    "reviews-mine": Entry({"GET": _case(SIGNED_IN)}),
    "reviews-submit": Entry({"POST": _case(REVIEWER, data={})}),
    "reviews-resubmit": Entry({"POST": _case(SIGNED_IN, data={})}),
    "reviews-analytics": Entry({"GET": _case(row(ANON, DENY, DENY, DENY, STUB, STUB, STUB, STUB, DENY))}),
    "pin-generate": Entry({"POST": _case(READS_RECORD, data={"record_id": Ref("record")}, objects=("record",))}),
    "pin-verify": Entry({"POST": _case(SIGNED_IN, data={"record_id": Ref("record"), "pin": "invalid"})}),
    "assignment-claim": Entry({"POST": _case(row(ANON, HIDE, DENY, DENY, OK, OK, OK, DENY, HIDE), kwargs=ASSIGNMENT, data={})}),
    "assignment-assign": Entry({m: _case(COORDINATOR, kwargs=ASSIGNMENT,
                                       **({} if m == "GET" else {"data": {"reviewer": Ref("reviewer_target")}}))
                               for m in ("GET", "POST")}),
    "assignment-add-reviewer": Entry({m: _case(SEAT_ACTS, kwargs=ASSIGNMENT,
                                             **({} if m == "GET" else {"data": {"reviewer": Ref("reviewer_target")}}))
                                     for m in ("GET", "POST")}),
    "seat-open": Entry({"POST": _case(SEAT_ACTS, kwargs=SEAT, data={})}),
    "seat-reassign": Entry({"POST": _case(COORDINATOR, kwargs=SEAT, data={"reviewer": Ref("reviewer_target")})}),
    "seat-withdraw": Entry({"POST": _case(COORDINATOR, kwargs=SEAT, data={})}),
}

AI = {
    "ai-ask": Entry({"POST": [
        _case(SIGNED_IN, data={"question": ""}),
        _case(PRIVATE, data={"question": "What is this research?", "conversation_id": Ref("conversation")}, objects=("conversation",)),
    ]}),
    "ai-ask-stream": Entry({"POST": [
        _case(SIGNED_IN, data={"question": ""}),
        _case(PRIVATE, data={"question": "What is this research?", "conversation_id": Ref("conversation")}, objects=("conversation",)),
    ]}),
    "ai-search": Entry({"POST": _case(SIGNED_IN, data={"query": ""})}),
    "ai-status": Entry({"GET": _case(SIGNED_IN)}),
    "ai-paper-brief": Entry({"POST": _case(READS_RECORD, kwargs=RECORD, data={})}),
    "ai-record-overview": Entry({"GET": _case(READS_RECORD, kwargs=RECORD)}),
    "ai-conversations": Entry({"GET": _case(SIGNED_IN), "POST": _case(SIGNED_IN, data={"title": "Matrix"})}),
    "ai-conversation-detail": Entry({m: _case(PRIVATE, kwargs={"pk": Ref("conversation")},
                                            **({} if m in ("GET", "DELETE") else {"data": {"title": "Renamed"}}))
                                    for m in ("GET", "PUT", "PATCH", "DELETE")}),
    "ai-research-run": Entry({"GET": _case(PRIVATE, kwargs={"pk": Ref("research_run")})}),
    "ai-ask-run-stream": Entry({"GET": _case(PRIVATE, kwargs={"pk": Ref("ask_run")})}),
    "ai-ask-run-cancel": Entry({"POST": _case(PRIVATE, kwargs={"pk": Ref("ask_run")}, data={})}),
    "ai-ask-run-retry": Entry({"POST": _case(PRIVATE, kwargs={"pk": Ref("ask_run")}, data={})}),
    "ai-embed-record": Entry({"POST": _case(OFFICE_ONLY, kwargs=RECORD, data={})}),
    "ai-embed-all": Entry({"POST": _case(OFFICE_ONLY, data={})}),
    "ai-embed-jobs": Entry({"GET": _case(OFFICE_ONLY)}),
}

NOTIFICATIONS = {
    "notification-list": Entry({"GET": _case(SIGNED_IN)}),
    "notification-read": Entry({"PATCH": [
        _case(PRIVATE, kwargs={"pk": Ref("notification")}, data={}),
        _case(row(ANON, OK, OK, HIDE, HIDE, HIDE, HIDE, HIDE, HIDE), kwargs={"pk": Ref("student_broadcast")}, data={}),
        _case(row(ANON, HIDE, HIDE, HIDE, OK, OK, OK, HIDE, HIDE), kwargs={"pk": Ref("office_broadcast")}, data={}),
    ]}),
    "notification-mark-all-read": Entry({"POST": _case(SIGNED_IN, data={})}),
}
OPPORTUNITIES = {
    "opportunity-list": Entry({"GET": _case(SIGNED_IN), "POST": _case(POSTER, data={"title": "Call"})}),
    # IR-121: an Adviser edits only their own call; RDCO moderates either.
    "opportunity-detail": Entry({m: [
        _case(SIGNED_IN if m == "GET" else RDCO_ONLY, kwargs={"pk": Ref("opportunity")},
              **({"data": {"title": "Updated"}} if m in ("PUT", "PATCH") else {})),
        _case(SIGNED_IN if m == "GET" else POSTER, kwargs={"pk": Ref("adviser_opportunity")},
              **({"data": {"title": "Updated"}} if m in ("PUT", "PATCH") else {})),
    ] for m in ("GET", "PUT", "PATCH", "DELETE")}),
    "opportunity-calendar": Entry({"GET": _case(SIGNED_IN, kwargs={"pk": Ref("opportunity")})}),
    "api-root": Shadowed(by="opportunity-list", why="The empty-prefix list matches before the router root."),
}
TABLE: dict[str, dict[str, Entry | Shadowed]] = {
    "records": RECORDS, "documents": DOCUMENTS_APP, "accounts": ACCOUNTS,
    "reviews": REVIEWS, "ai": AI, "notifications": NOTIFICATIONS,
    "audit": {"audit-list": Entry({"GET": _case(RDCO_ONLY)})},
    "opportunities": OPPORTUNITIES,
}
DECLARED = TABLE
