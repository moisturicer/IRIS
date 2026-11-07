"""
A person's public profile: who has one, what it lists, and how a list pages
(IR-696, spec IR-694).

Two rules live here and nowhere else, so every route and every `has_profile`
flag agrees:

* **Who has a profile** (`open_profiles`). An active, verified, unlocked
  Student, Adviser or office member. A suspended, inactive, unverified or
  unapproved (role-less) account and the System Admin have none; asking for
  one is the same 404 as a missing id, so the API never confirms a hidden
  account exists.
* **Which papers it lists** (`published_papers`). Discover's own predicate --
  `Record.objects.visible_to(viewer)` narrowed to the published catalogue --
  so a draft, a paper under review, an unlisted or rejected one never appears,
  with Proposals and soft-deleted papers excluded as well.

Nothing here returns an email address, coordinator status, lock state or any
other account detail: each payload is built field by field, not by serializing
the account, so a field added to `User` later cannot leak through it.
"""

from __future__ import annotations

from collections import Counter

from django.db.models import Prefetch, Q
from django.http import Http404
from rest_framework.exceptions import ValidationError
from rest_framework.utils.urls import replace_query_param

from apps.records.models import Author, Record, RecordOwner
from core.enums import PUBLICLY_VISIBLE_STATUSES, RecordTypeName, RoleName

from . import profile
from .models import User

#: Roles a profile is shown for. The System Admin runs IRIS and holds no
#: workflow access, so it has none; a role-less account is still unapproved.
PROFILE_ROLES = (
    RoleName.STUDENT, RoleName.ADVISER, RoleName.ITSO, RoleName.IERC, RoleName.KTTO, RoleName.RDCO,
)

PAPERS_PAGE_SIZE = 10
COLLABORATORS_PAGE_SIZE = 12
#: Larger than any screen asks for; a bigger request is capped, not refused.
MAX_PAGE_SIZE = 50

BAD_PAGE = "page must be a whole number of 1 or more."
BAD_PAGE_SIZE = "page_size must be a whole number of 1 or more."


# -- Who has a profile ---------------------------------------------------------

def open_profiles():
    """The accounts whose profile may be read. The one predicate."""
    return User.objects.filter(
        is_active=True, is_locked=False, is_verified=True, role__name__in=PROFILE_ROLES,
    )


def person_or_404(pk: int) -> User:
    """The person with an open profile, or the 404 a missing id gets."""
    person = (
        open_profiles()
        .select_related(
            "role", "student_profile__course__department__college",
            "adviser_profile__college", "adviser_profile__department",
        )
        .filter(pk=pk)
        .first()
    )
    if person is None:
        raise Http404
    return person


def open_profile_ids(record: Record) -> set[int]:
    """
    Which of `record`'s Adviser and owners have a profile that opens, for the
    flags on its detail. Empty unless the paper is itself one a profile lists:
    a name on a draft or a paper in review never links.
    """
    if not is_listed(record):
        return set()
    ids = {owner.user_id for owner in record.owners.all()}
    if record.adviser_id is not None:
        ids.add(record.adviser_id)
    return set(open_profiles().filter(pk__in=ids).values_list("pk", flat=True))


# -- The person ----------------------------------------------------------------

def profile_payload(person: User) -> dict:
    affiliation = profile.affiliation(person)
    return {
        "id": person.pk,
        "first_name": person.first_name,
        "middle_initial": person.middle_initial,
        "last_name": person.last_name,
        # `Student`, `Adviser` or the office's name: the stored role, which is
        # the label for every role `open_profiles` admits.
        "role_label": person.role.name,
        "college_name": affiliation.college,
        "department_name": affiliation.department,
        "course_name": affiliation.course,
        "bio": person.bio,
        "research_interests": profile.interest_names(person),
        "photo_url": profile.photo_url(person),
    }


# -- Their papers --------------------------------------------------------------

def is_listed(record: Record) -> bool:
    """
    Is `record` one a profile lists? The per-record form of `published_papers`:
    keep the two together, since the flags on a record and the lists must agree.
    """
    if record.pipeline_status not in PUBLICLY_VISIBLE_STATUSES:
        return False
    return record.record_type is None or record.record_type.name != RecordTypeName.PROPOSAL


def published_papers(viewer: User):
    """What Discover lists for `viewer`, without Proposals. See `is_listed`."""
    return (
        Record.objects.visible_to(viewer)
        .filter(pipeline_status__in=PUBLICLY_VISIBLE_STATUSES)
        .exclude(record_type__name=RecordTypeName.PROPOSAL)
    )


def _newest_first(papers):
    # Discover's own order: there is no separate publication timestamp.
    return (
        papers.select_related("classification", "record_type")
        .prefetch_related(Prefetch("authors", queryset=Author.objects.order_by("pk")))
        .order_by("-created_at", "-pk")
    )


def research_papers(viewer: User, person: User):
    """Published papers `person` owns, newest first."""
    return _newest_first(published_papers(viewer).filter(owners__user=person))


def advised_papers(viewer: User, person: User):
    """Published papers `person` was the Adviser on, newest first."""
    return _newest_first(published_papers(viewer).filter(adviser=person))


def paper_payload(record: Record) -> dict:
    return {
        "id": record.pk,
        "title": record.title,
        "authors": [author.name for author in record.authors.all()],
        "classification_name": record.classification.name if record.classification else "",
        "record_type_name": record.record_type.name if record.record_type else "",
        "publication_year": record.publication_year,
        "views": record.access_count,
    }


# -- Their collaborators -------------------------------------------------------

def collaborators(viewer: User, person: User) -> list[tuple[User, int]]:
    """
    Accounts that shared a published paper with `person`, most papers first.

    Two people share a paper when both are among its owners or its Adviser --
    co-owners, or an Adviser and an owner (an advisee). Byline authors are
    names, not accounts, and never count. An account without an open profile is
    left out, so a collaborator is always someone whose page opens.
    """
    paper_ids = list(
        published_papers(viewer)
        .filter(Q(owners__user=person) | Q(adviser=person))
        .values_list("pk", flat=True)
    )
    pairs = set(
        RecordOwner.objects.filter(record_id__in=paper_ids)
        .exclude(user=person)
        .values_list("user_id", "record_id")
    )
    pairs |= set(
        Record.objects.filter(pk__in=paper_ids, adviser__isnull=False)
        .exclude(adviser=person)
        .values_list("adviser_id", "pk")
    )
    shared = Counter(user_id for user_id, _ in pairs)  # a pair is counted once per paper
    people = open_profiles().filter(pk__in=list(shared))
    return sorted(
        ((user, shared[user.pk]) for user in people),
        key=lambda row: (-row[1], row[0].last_name.casefold(), row[0].first_name.casefold(), row[0].pk),
    )


def collaborator_payload(user: User, shared_papers: int) -> dict:
    return {
        "id": user.pk,
        "first_name": user.first_name,
        "middle_initial": user.middle_initial,
        "last_name": user.last_name,
        "photo_url": profile.photo_url(user),
        "shared_papers": shared_papers,
    }


# -- Paging --------------------------------------------------------------------

def _whole_number(raw, message: str, field: str) -> int:
    try:
        value = int(raw)
    except (TypeError, ValueError):
        raise ValidationError({field: [message]})
    if value < 1:
        raise ValidationError({field: [message]})
    return value


def paginate(request, rows, default_size: int, build) -> dict:
    """
    One page of `rows`, each passed through `build`, as `{"next", "results"}`,
    with no total.

    `next` is the URL of the following page, or `None` on the last; nothing on
    the page shows a count, so none is computed (one extra row is read to know
    whether another page exists). A page past the end is empty, not an error:
    a paper may leave the list between two reads.
    """
    params = request.query_params
    page = _whole_number(params.get("page", 1), BAD_PAGE, "page")
    size = min(_whole_number(params.get("page_size", default_size), BAD_PAGE_SIZE, "page_size"), MAX_PAGE_SIZE)
    start = (page - 1) * size
    window = list(rows[start:start + size + 1])
    following = None
    if len(window) > size:
        following = replace_query_param(request.build_absolute_uri(), "page", page + 1)
    return {"next": following, "results": [build(row) for row in window[:size]]}
