"""
The export itself: one dict of one person's own data (ADR-051 decision 13, IR-786).

**Three rules decide what goes in.**

1. *It is the person's own.* Every query starts from the signed-in user. Other
   people appear only as a count or a yes/no (`other_owner_count`,
   `uploaded_by_you`), never by name, email or id -- the other owners of a paper,
   the Adviser, a reviewer who judged it, the staff who decided a request.
2. *It is what they wrote or chose,* not what the system derived. Indexes,
   vectors and summaries are left out (see `registry.EXCLUDED`).
3. *It is checked against now.* A paper the person can no longer read appears
   by id only, and a Conversation Turn that cites one stays out, the same rule
   a reopened Conversation follows (`apps.ai.history.readable_record_ids`).

**No credential is ever read.** The queries below name the fields they take; none
selects `password`, a token, a grant or a recovery secret, and the account
section is a hand-written allowlist, not a serializer over `User`.

Each section is a function returning JSON-ready data. A section name here is
what `registry.INCLUDED` points at.
"""

from __future__ import annotations

from typing import Callable, Iterable

from django.utils import timezone

from core.enums import Office

EXPORT_FORMAT = "iris-personal-data-1"


# -- shared helpers -----------------------------------------------------------

def _name(obj):
    return obj.name if obj is not None else None


def _readable_titles(user, record_ids: Iterable[int]) -> dict[int, str]:
    """Title of each Record among `record_ids` that `user` may read now.

    The one predicate Ask IRIS reopens a Conversation by. A Record missing from
    the result is gone or unreadable, and callers show its id and nothing else.
    """
    from apps.ai.history import readable_record_ids
    from apps.records.models import Record

    ids = set(record_ids)
    allowed = readable_record_ids(user, ids)
    return dict(Record.objects.filter(pk__in=allowed).values_list("pk", "title"))


def _paper(record_id, titles: dict[int, str]) -> dict:
    """A reference to a paper that is not the person's own."""
    title = titles.get(record_id)
    return {"record_id": record_id, "title": title, "available": title is not None}


# -- account ------------------------------------------------------------------

def account(user) -> dict:
    from apps.accounts.models import AccountDeletionRequest, AdviserProfile, RoleRequest, StudentProfile

    data = {
        "id": user.pk,
        "email": user.email,
        "first_name": user.first_name,
        "middle_initial": user.middle_initial,
        "last_name": user.last_name,
        "role": _name(user.role),
        "is_office_coordinator": user.is_office_coordinator,
        "is_verified": user.is_verified,
        "is_active": user.is_active,
        "date_joined": user.date_joined,
        "signup_consent_given": user.consent_given,
        # The optional profile (IR-695). The photo is a file served only through
        # Django, so the download says whether there is one, not its bytes.
        "bio": user.bio,
        "has_photo": bool(user.photo),
        "research_interests": [
            row.interest.name
            for row in user.interest_links.select_related("interest").order_by("position")
        ],
        "student_profile": None,
        "adviser_profile": None,
    }
    student = (StudentProfile.objects.filter(user=user)
               .select_related("course__department__college").first())
    if student is not None:
        course = student.course
        data["student_profile"] = {
            "course": _name(course),
            "department": _name(course.department) if course else None,
            "college": _name(course.department.college) if course else None,
        }
    adviser = (AdviserProfile.objects.filter(user=user)
               .select_related("department", "college").first())
    if adviser is not None:
        data["adviser_profile"] = {
            "department": _name(adviser.department),
            "college": _name(adviser.college),
        }
    data["role_requests"] = [
        {
            "requested_role": row.requested_role.name,
            "status": row.status,
            "created_at": row.created_at,
            "reviewed_at": row.reviewed_at,
        }
        for row in RoleRequest.objects.filter(user=user).select_related("requested_role").order_by("id")
    ]
    # Their own requests to delete the account (IR-785). Who decided is left
    # out, as with role requests; a rejection's reason is theirs to read.
    data["deletion_requests"] = [
        {
            "status": row.status,
            "created_at": row.created_at,
            "decided_at": row.decided_at,
            "reason": row.reason,
        }
        for row in AccountDeletionRequest.objects.filter(user=user).order_by("id")
    ]
    return data


def sessions(user) -> list[dict]:
    from apps.accounts.models import UserSession

    return [
        {
            "signed_in_at": row.created_at,
            "last_activity_at": row.last_activity_at,
            "ended_at": row.ended_at,
            "ended_reason": row.ended_reason,
        }
        for row in UserSession.objects.filter(user=user).order_by("id")
    ]


# -- papers -------------------------------------------------------------------

def papers_owned(user) -> list[dict]:
    """Each paper the person owns, in full: its details, versions and files.

    Soft-deleted papers stay in, flagged. Other owners and the Adviser are not
    named: the paper says only how many other owners it has, and whether it has
    an Adviser (and whether that is the person themself).
    """
    from apps.documents.models import RecordFile, RecordUpload
    from apps.records.models import Record, RecordOwner

    memberships = {
        row.record_id: row.is_primary
        for row in RecordOwner.objects.filter(user=user)
    }
    records = (
        Record.objects.with_deleted().filter(pk__in=memberships)
        .select_related("classification", "psced", "record_type")
        .prefetch_related("authors__role", "conferences__level", "versions__documents")
        .select_related("publication__level", "linked_thesis", "linked_proposal")
        .order_by("id")
    )
    other_owners = {}
    for record_id, owner_id in RecordOwner.objects.filter(record_id__in=memberships).values_list(
        "record_id", "user_id"
    ):
        if owner_id != user.pk:
            other_owners[record_id] = other_owners.get(record_id, 0) + 1

    files = {}
    for row in RecordFile.objects.filter(record_id__in=memberships).order_by("id"):
        files.setdefault(row.record_id, []).append({
            "filename": row.filename,
            "party": row.party,
            "added_at": row.created_at,
            "uploaded_by_you": row.uploaded_by_id == user.pk,
        })
    uploads = {}
    for row in (RecordUpload.objects.filter(record_id__in=memberships)
                .select_related("slot", "status").order_by("id")):
        uploads.setdefault(row.record_id, []).append({
            "id": row.pk,
            "slot": _name(row.slot),
            "version": row.version,
            "status": _name(row.status),
            "added_at": row.created_at,
            "uploaded_by_you": row.uploaded_by_id == user.pk,
        })

    out = []
    for record in records:
        publication = getattr(record, "publication", None)
        out.append({
            "id": record.pk,
            "title": record.title,
            "abstract": record.abstract,
            "keywords": record.keywords,
            "record_type": _name(record.record_type),
            "classification": _name(record.classification),
            "psced": _name(record.psced),
            "publication_year": record.publication_year,
            "year_accomplished": record.year_accomplished,
            "year_completed": record.year_completed,
            "is_ip": record.is_ip,
            "ip_type": record.ip_type,
            "for_commercialization": record.for_commercialization,
            "community_extension": record.community_extension,
            "requires_ethics_review": record.requires_ethics_review,
            "requested_offices": {
                Office.ITSO.value: record.requested_itso,
                Office.IERC.value: record.requested_ierc,
                Office.KTTO.value: record.requested_ktto,
            },
            "pipeline_status": record.pipeline_status,
            "resubmission_count": record.resubmission_count,
            "last_resubmitted_at": record.last_resubmitted_at,
            "embargo_state": record.embargo_state.value,
            "embargoed_until": record.embargoed_until,
            "embargo_date_set_at": record.embargo_date_set_at,
            "dpa_accepted_at": record.dpa_accepted_at,
            "manuscript_filename": record.manuscript_filename,
            "created_at": record.created_at,
            "updated_at": record.updated_at,
            "is_deleted": record.is_deleted,
            "deleted_at": record.deleted_at,
            "you_are_primary_owner": memberships[record.pk],
            "other_owner_count": other_owners.get(record.pk, 0),
            "has_adviser": record.adviser_id is not None,
            "you_are_adviser": record.adviser_id == user.pk,
            "authors": [
                {"name": author.name, "role": _name(author.role)}
                for author in sorted(record.authors.all(), key=lambda a: a.pk)
            ],
            "publication": None if publication is None else {
                "isbn": publication.isbn,
                "issn": publication.issn,
                "isi": publication.isi,
                "year_published": publication.year_published,
                "level": _name(publication.level),
            },
            "conferences": [
                {
                    "title": conference.title,
                    "date": conference.date,
                    "venue": conference.venue,
                    "level": _name(conference.level),
                }
                for conference in sorted(record.conferences.all(), key=lambda c: c.pk)
            ],
            "versions": [
                {
                    "number": version.number,
                    "cause": version.cause,
                    "manuscript_filename": version.manuscript_filename,
                    "created_at": version.created_at,
                    "created_by_you": version.created_by_id == user.pk,
                    "upload_ids": sorted(doc.upload_id for doc in version.documents.all()),
                }
                for version in sorted(record.versions.all(), key=lambda v: v.number)
            ],
            "files": files.get(record.pk, []),
            "uploads": uploads.get(record.pk, []),
            "continues_proposal_id": record.derived_from_id,
            "linked_thesis_id": getattr(getattr(record, "linked_thesis", None), "thesis_id", None),
            "linked_proposal_id": getattr(getattr(record, "linked_proposal", None), "proposal_id", None),
        })
    return out


def saved_papers(user) -> list[dict]:
    from apps.library.models import SavedRecord

    rows = list(SavedRecord.objects.filter(owner=user).order_by("id"))
    titles = _readable_titles(user, [row.record_id for row in rows])
    return [
        {
            **_paper(row.record_id, titles),
            "reading_status": row.reading_status,
            "saved_at": row.saved_at,
            "updated_at": row.updated_at,
        }
        for row in rows
    ]


def papers_viewed(user) -> list[dict]:
    """The published papers the person has opened, each counted once as a View
    (IR-369), and when they first opened it. The title is given only while they
    may still read the paper."""
    from apps.records.models import RecordView

    rows = list(RecordView.objects.filter(user=user).order_by("id"))
    titles = _readable_titles(user, [row.record_id for row in rows])
    return [{**_paper(row.record_id, titles), "first_viewed_at": row.viewed_at} for row in rows]


def reading_notes(user) -> list[dict]:
    """
    The person's own private notes (IR-580, ADR-064 §8): the text they typed and
    its revision. The Record's title is given only while they may still read it;
    the note text is theirs either way (the retention rule, §6).
    """
    from apps.library.models import ReadingNote

    rows = list(ReadingNote.objects.filter(owner=user).order_by("id"))
    titles = _readable_titles(user, [row.record_id for row in rows])
    return [
        {
            **_paper(row.record_id, titles),
            "body": row.body,
            "revision": row.revision,
            "created_at": row.created_at,
            "updated_at": row.updated_at,
        }
        for row in rows
    ]


def reading_highlights(user) -> list[dict]:
    """
    The person's own highlights (IR-583, ADR-065 §7): the page of each passage
    they saved and, while they may still read the Record, its quotation. The
    quotation is a copy of the paper, so it is withheld once the Record is
    unreadable; the fact that they saved something on that page is theirs.
    """
    from apps.library.models import ReadingHighlight

    rows = list(ReadingHighlight.objects.filter(owner=user).order_by("id"))
    titles = _readable_titles(user, [row.record_id for row in rows])
    return [
        {
            **_paper(row.record_id, titles),
            "page": row.page,
            "quote": row.quote if row.record_id in titles else None,
            "created_at": row.created_at,
        }
        for row in rows
    ]


def saved_feeds(user) -> list[dict]:
    """The person's private custom feeds: the name they gave and the filters they saved."""
    from apps.library.models import SavedFeed

    return [
        {"name": row.name, "query": row.query, "created_at": row.created_at, "updated_at": row.updated_at}
        for row in SavedFeed.objects.filter(owner=user).order_by("id")
    ]


def saved_replies(user) -> list[dict]:
    """The person's own reusable review texts (IR-877): the title and the text."""
    from apps.reviews.models import SavedReply

    return [
        {"title": row.title, "body": row.body, "created_at": row.created_at, "updated_at": row.updated_at}
        for row in SavedReply.objects.filter(owner=user).order_by("id")
    ]


def viewed_marks(user) -> list[dict]:
    """The sections the person ticked as viewed in a review comparison (IR-877):
    which paper and Version, and the section's heading as the reader keyed it."""
    from apps.reviews.models import ViewedMark

    return [
        {"record_id": row.record_id, "version": row.version.number, "section": row.section_key,
         "created_at": row.created_at}
        for row in ViewedMark.objects.filter(user=user).select_related("version").order_by("id")
    ]


def review_mentions(user) -> list[dict]:
    """Where the person was mentioned in a review discussion (IR-877): the paper
    and when they were told. A draft's mention is its writer's until it is sent,
    so only mentions the person was told of are theirs; the comment and its
    writer are not named."""
    from apps.reviews.models import ReviewMention

    rows = list(ReviewMention.objects.filter(user=user, notified_at__isnull=False)
                .select_related("comment").order_by("id"))
    titles = _readable_titles(user, [row.comment.record_id for row in rows])
    return [{"paper": _paper(row.comment.record_id, titles), "at": row.notified_at} for row in rows]


def comments(user) -> list[dict]:
    """The Comments the person wrote on published papers (IR-690). A deleted or
    removed one is listed without its text, which no response ever carries."""
    from apps.records.models import PublicComment

    rows = list(PublicComment.objects.filter(author=user).order_by("id"))
    titles = _readable_titles(user, [row.record_id for row in rows])
    return [
        {"paper": _paper(row.record_id, titles), "body": None if row.deletion_kind else row.body,
         "is_reply": row.reply_to_id is not None, "deletion": row.deletion_kind,
         "at": row.created_at, "edited_at": row.edited_at}
        for row in rows
    ]


def discovery(user) -> dict:
    from apps.records.models import DiscoveryDismissal, DiscoveryInterests

    interests = (DiscoveryInterests.objects.filter(user=user)
                 .prefetch_related("classifications", "psced").first())
    dismissals = list(DiscoveryDismissal.objects.filter(user=user).order_by("id"))
    titles = _readable_titles(user, [row.record_id for row in dismissals])
    return {
        "interests": None if interests is None else {
            "classifications": sorted(c.name for c in interests.classifications.all()),
            "psced": sorted(p.name for p in interests.psced.all()),
        },
        "not_interested": [
            {**_paper(row.record_id, titles), "at": row.created_at} for row in dismissals
        ],
    }


# -- Ask IRIS -----------------------------------------------------------------

def _turn_record_ids(turn) -> set[int]:
    """Every paper a Turn rests on: its citations, its listing and its comparison."""
    ids = {citation.record_id for citation in turn.citations.all()}
    listing = turn.listing if isinstance(turn.listing, dict) else {}
    for row in (*listing.get("records", []), *listing.get("candidates", [])):
        if isinstance(row, dict) and isinstance(row.get("record_id"), int):
            ids.add(row["record_id"])
    comparison = turn.comparison if isinstance(turn.comparison, dict) else {}
    for version in comparison.get("source_versions", []) or []:
        if isinstance(version, dict) and isinstance(version.get("record_id"), int):
            ids.add(version["record_id"])
    return ids


def conversations(user) -> list[dict]:
    """The person's Ask IRIS Conversations, minus any Turn resting on an unreadable paper.

    A Turn is kept or dropped whole, never edited: an answer derived from a
    paper the person can no longer read would still carry it.
    """
    from apps.ai.history import readable_record_ids
    from apps.ai.models import Conversation

    rows = list(
        Conversation.objects.filter(user=user)
        .prefetch_related("turns__citations").order_by("id")
    )
    turns = [turn for conversation in rows for turn in conversation.turns.all()]
    needed = {record_id for turn in turns for record_id in _turn_record_ids(turn)}
    needed |= {c.record_id for c in rows if c.record_id is not None}
    readable = readable_record_ids(user, needed)
    from apps.records.models import Record
    titles = dict(Record.objects.filter(pk__in=readable).values_list("pk", "title"))

    out = []
    for conversation in rows:
        kept, left_out = [], 0
        for turn in conversation.turns.all():
            if not _turn_record_ids(turn) <= readable:
                left_out += 1
                continue
            kept.append({
                "id": turn.pk,
                "asked_at": turn.created_at,
                "question": turn.question,
                "resolved_question": turn.resolved_question or None,
                "answer": turn.answer or None,
                "state": turn.state,
                "citations": [
                    {
                        "marker": citation.marker,
                        "record_id": citation.record_id,
                        "title": titles.get(citation.record_id),
                        "page": citation.page,
                    }
                    for citation in turn.citations.all()
                ],
            })
        out.append({
            "id": conversation.pk,
            "title": conversation.title,
            "about_paper": None if conversation.record_id is None else _paper(conversation.record_id, titles),
            "created_at": conversation.created_at,
            "updated_at": conversation.updated_at,
            "turns": kept,
            "turns_left_out": left_out,
        })
    return out


# -- requests -----------------------------------------------------------------

def download_requests(user) -> list[dict]:
    from apps.records.models import DownloadRequest

    rows = list(DownloadRequest.objects.filter(requested_by=user).order_by("id"))
    titles = _readable_titles(user, [row.record_id for row in rows])
    return [
        {
            "id": row.pk,
            "paper": _paper(row.record_id, titles),
            "status": row.status,
            "your_note": row.note,
            "office_note": row.rdco_note,
            "requested_at": row.created_at,
            "decided_at": row.reviewed_at,
            "access_expires_at": row.grant_expires_at,
            "revoked_at": row.revoked_at,
            "cancelled_at": row.cancelled_at,
        }
        for row in rows
    ]


def delete_requests(user) -> list[dict]:
    from apps.records.models import DeleteRequest

    rows = list(DeleteRequest.objects.filter(requested_by=user).order_by("id"))
    titles = _readable_titles(user, [row.record_id for row in rows])
    return [
        {
            "id": row.pk,
            "paper": _paper(row.record_id, titles),
            "reason": row.reason,
            "status": row.status,
            "requested_at": row.created_at,
            "decided_at": row.reviewed_at,
        }
        for row in rows
    ]


# -- notifications and postings -----------------------------------------------

def notifications(user) -> dict:
    """Notices sent to the person, with when they read each. The sender is not named."""
    from apps.notifications.models import Notification, NotificationRead

    read_at = dict(NotificationRead.objects.filter(user=user).values_list("notification_id", "read_at"))
    received = list(
        Notification.objects.filter(recipient=user).select_related("notif_type").order_by("id")
    )
    titles = _readable_titles(user, [row.record_id for row in received if row.record_id])
    return {
        "received": [
            {
                "id": row.pk,
                "type": _name(row.notif_type),
                "message": row.message,
                "paper": None if row.record_id is None else _paper(row.record_id, titles),
                "sent_at": row.created_at,
                "read_at": read_at.get(row.pk),
            }
            for row in received
        ],
        "read_receipts": [
            {"notification_id": notification_id, "read_at": stamp}
            for notification_id, stamp in sorted(read_at.items())
        ],
    }


def opportunities_posted(user) -> list[dict]:
    from apps.opportunities.models import Opportunity

    return [
        {
            "id": row.pk,
            "type": row.opportunity_type,
            "title": row.title,
            "posting_office": row.posting_office,
            "audience": row.audience,
            "description": row.description,
            "external_url": row.external_url,
            "due_date": row.due_date,
            "tags": row.tags,
            "posted_at": row.created_at,
            "updated_at": row.updated_at,
        }
        for row in Opportunity.objects.filter(posted_by=user).order_by("id")
    ]


# -- acts as an Adviser or office reviewer -------------------------------------

def workflow_acts(user) -> dict:
    """What the person wrote as an Adviser or office reviewer, and only that.

    The papers are other people's, so each is named only while the person may
    still read it. Replies others wrote under the person's comments are not
    here, and nor are the decisions others took on the same papers.
    """
    from apps.documents.models import DocumentRequest, UploadReview
    from apps.reviews.models import (
        RecordClearance, ResubmissionRequest, Review, ReviewComment, ReviewRound, RoutingEvent,
    )

    reviews = list(Review.objects.filter(reviewed_by=user).order_by("id"))
    comments = list(ReviewComment.objects.filter(author=user).order_by("id"))
    clearances = list(RecordClearance.objects.filter(reviewed_by=user).order_by("id"))
    revisions = list(ResubmissionRequest.objects.filter(requested_by=user).order_by("id"))
    routings = list(RoutingEvent.objects.filter(actor=user).order_by("id"))
    rounds = list(ReviewRound.objects.filter(actor=user).order_by("id"))
    doc_requests = list(
        DocumentRequest.objects.filter(requested_by=user).prefetch_related("items").order_by("id")
    )
    upload_reviews = list(
        UploadReview.objects.filter(reviewed_by=user).select_related("upload", "status").order_by("id")
    )
    titles = _readable_titles(user, {
        *(r.record_id for r in reviews), *(c.record_id for c in comments),
        *(c.record_id for c in clearances), *(r.record_id for r in revisions),
        *(r.record_id for r in routings), *(r.record_id for r in rounds),
        *(d.record_id for d in doc_requests),
        *(u.upload.record_id for u in upload_reviews),
    })
    return {
        "reviews": [
            {"paper": _paper(r.record_id, titles), "stage": r.stage, "decision": r.status,
             "comment": r.comment, "at": r.created_at}
            for r in reviews
        ],
        "review_comments": [
            {"paper": _paper(c.record_id, titles), "body": c.body, "suggestion": c.suggestion,
             "is_reply": c.reply_to_id is not None, "at": c.created_at}
            for c in comments
        ],
        "review_rounds": [
            {"paper": _paper(r.record_id, titles), "party": r.party, "verdict": r.verdict,
             "summary": r.summary, "at": r.created_at}
            for r in rounds
        ],
        "office_clearances": [
            {"paper": _paper(c.record_id, titles), "office": c.office, "status": c.status,
             "comment": c.comment, "at": c.updated_at}
            for c in clearances
        ],
        "revision_requests": [
            {"paper": _paper(r.record_id, titles), "party": r.party, "reason": r.reason,
             "state": r.state, "at": r.created_at}
            for r in revisions
        ],
        "routings": [
            {"paper": _paper(r.record_id, titles), "from": r.from_party, "to": r.to_party,
             "reason": r.reason, "at": r.created_at}
            for r in routings
        ],
        "document_requests": [
            {
                "paper": _paper(d.record_id, titles), "party": d.party, "message": d.message,
                "state": d.state, "at": d.created_at,
                "items": [
                    {"label": item.label, "state": item.state, "rejection_reason": item.rejection_reason}
                    for item in sorted(d.items.all(), key=lambda i: i.sort_order)
                ],
            }
            for d in doc_requests
        ],
        "upload_reviews": [
            {"paper": _paper(u.upload.record_id, titles), "status": _name(u.status),
             "comment": u.comment, "at": u.created_at}
            for u in upload_reviews
        ],
    }


# -- consent ------------------------------------------------------------------

def consent(user) -> dict:
    """What IRIS holds about the person's consent today.

    The notice answers (ADR-054, IR-789) are append-only, one row per answer to
    one notice version, so `history` is every answer the person has given. The
    signup yes/no and each paper's stamp are the older, unversioned records and
    stay as they were.
    """
    from apps.accounts.models import NoticeAnswer
    from apps.records.models import Record

    stamps = (Record.objects.with_deleted().filter(dpa_accepted_by=user)
              .exclude(dpa_accepted_at__isnull=True).order_by("id").values_list("pk", "dpa_accepted_at"))
    return {
        "signup_consent_given": user.consent_given,
        "paper_consents": [{"record_id": pk, "accepted_at": stamp} for pk, stamp in stamps],
        "answered_notice_version": user.answered_notice_version,
        "ai_consent": user.ai_consent,
        "notice_answered_at": user.notice_answered_at,
        "history": [
            {
                "notice_version": row.notice.number,
                "agreed_data_privacy_agreement": row.agreed_dpa,
                "ai_consent": row.ai_consent,
                "answered_at": row.answered_at,
            }
            for row in NoticeAnswer.objects.filter(user=user).select_related("notice").order_by("id")
        ],
    }


# -- assembly -----------------------------------------------------------------

#: Section name -> builder. `registry.INCLUDED` values must be keys of this.
SECTIONS: dict[str, Callable] = {
    "account": account,
    "sessions": sessions,
    "papers_owned": papers_owned,
    "saved_papers": saved_papers,
    "papers_viewed": papers_viewed,
    "saved_feeds": saved_feeds,
    "reading_notes": reading_notes,
    "reading_highlights": reading_highlights,
    "saved_replies": saved_replies,
    "viewed_marks": viewed_marks,
    "review_mentions": review_mentions,
    "comments": comments,
    "discovery": discovery,
    "conversations": conversations,
    "download_requests": download_requests,
    "delete_requests": delete_requests,
    "notifications": notifications,
    "opportunities_posted": opportunities_posted,
    "workflow_acts": workflow_acts,
    "consent": consent,
}

LEFT_OUT = [
    "Other people's data: other owners of your papers, an Adviser's or reviewer's details, "
    "and review comments or notes written by anyone else.",
    "Credentials: your password, sign-in tokens and recovery secrets.",
    "Data the system made from your papers, such as search indexes, vectors and summaries.",
    "The Audit Log, which belongs to the System Admin. This download is recorded in it.",
    "Comments and notes you write on papers: not part of IRIS yet.",
]


def build_export(user) -> dict:
    payload = {
        "format": EXPORT_FORMAT,
        "exported_at": timezone.now(),
        "left_out": LEFT_OUT,
    }
    for name, builder in SECTIONS.items():
        payload[name] = builder(user)
    return payload
