"""
The review workspace sidebar's paper details (ADR-032 §10 Amendment, IR-686).

Record detail's `paper_details` block: the record's college and program, the
offices the author's ADR-018 hints point to, a profile card for every person,
everyone in the review, and each running party's due date. The client renders
it and assembles none of it.

A profile card carries only fields the viewer may already read elsewhere:

- an owner's email rides on `owners` to anyone who reads the record;
- an Adviser's email, college and department are on `GET /users/advisers/`,
  open to every signed-in user (IR-540's notice);
- a reviewer's name and office are review content, on the tracker under
  `may_read_review`; nothing else of theirs is;
- the person themself (`/auth/me/`) and RDCO (the user list) read it all.

Participants and due dates are review content: `None` -- not disclosed,
which is not `[]` -- to a viewer `may_read_review` refuses.
"""
from typing import Optional

from apps.reviews.models import ReviewerSeat
from apps.reviews.routing import _HINT_FIELD, _HINT_TEXT
from core.enums import Party, RoleName, SeatState
from core.permissions import ADMIN_ROLES, get_role_name

#: Every field a card may carry; a withheld one is null.
CARD_FIELDS = ("college", "department", "program", "email")


def _profile(user) -> dict:
    """What IRIS holds of `user`'s affiliation, whether or not it is shown."""
    facts = {"college": None, "department": None, "program": None, "email": user.email}
    student = getattr(user, "student_profile", None)
    course = getattr(student, "course", None)
    if course is not None:
        facts["program"] = course.name
        facts["department"] = course.department.name
        facts["college"] = course.department.college.name
    adviser = getattr(user, "adviser_profile", None)
    if adviser is not None:
        facts["department"] = facts["department"] or getattr(adviser.department, "name", None)
        facts["college"] = facts["college"] or getattr(adviser.college, "name", None)
    return facts


def _reads_everything(viewer, user) -> bool:
    return bool(viewer and getattr(viewer, "pk", None) == user.pk) or get_role_name(viewer) in ADMIN_ROLES


def _listed_adviser(user) -> bool:
    """On the adviser picker: an active user whose role is Adviser."""
    return user.is_active and get_role_name(user) == RoleName.ADVISER


def card(user, viewer, *, role: str, office: Optional[str] = None, public=()) -> dict:
    """One person's card: `public` names the fields this viewer may read anyway."""
    facts = _profile(user)
    shown = set(CARD_FIELDS) if _reads_everything(viewer, user) else set(public)
    return {
        "id": user.pk,
        "name": user.get_full_name() or user.email,
        "role": role,
        "office": office,
        **{field: facts[field] if field in shown else None for field in CARD_FIELDS},
    }


def _owner_users(record) -> list:
    return [
        o.user for o in record.owners.select_related(
            "user__student_profile__course__department__college",
            "user__adviser_profile__college", "user__adviser_profile__department", "user__role",
        ).order_by("-is_primary", "pk")
    ]


def _researcher(user, viewer):
    return card(user, viewer, role="Researcher", public=("email",))


def _adviser(record, viewer):
    user = record.adviser
    if user is None:
        return None
    public = ("email", "college", "department") if _listed_adviser(user) else ()
    return card(user, viewer, role="Adviser", public=public)


def _participants(record, viewer, owners) -> list[dict]:
    """Owners, the Adviser, then everyone who has held a seat, once each."""
    people, seen = [], set()
    for user in owners:
        seen.add(user.pk)
        people.append(_researcher(user, viewer))
    if record.adviser_id and record.adviser_id not in seen:
        seen.add(record.adviser_id)
        people.append(_adviser(record, viewer))
    seats = (
        ReviewerSeat.objects.filter(assignment__record=record, reviewer__isnull=False)
        # A seat a coordinator withdrew is out, as on the tracker (IR-270).
        .exclude(state=SeatState.WITHDRAWN, closed_by_decision__isnull=True)
        .select_related(
            "assignment", "reviewer__student_profile__course__department__college",
            "reviewer__adviser_profile__college", "reviewer__adviser_profile__department",
        ).order_by("assigned_at", "pk")
    )
    for seat in seats:
        if seat.reviewer_id in seen:
            continue
        seen.add(seat.reviewer_id)
        office = str(Party(seat.assignment.party).label)
        people.append(card(seat.reviewer, viewer, role=f"{office} reviewer", office=office))
    return people


def _due_dates(deadlines: list[dict]) -> list[dict]:
    keys = ("due_at", "original_due_at", "is_overdue", "clock_paused")
    return [
        {"party": d["party"], "label": str(Party(d["party"]).label), **{k: d[k] for k in keys}}
        for d in deadlines if d["due_at"] or d["clock_paused"]
    ]


def _distinct(values) -> list[str]:
    return list(dict.fromkeys(v for v in values if v))


def paper_details(record, viewer, *, readable: bool, deadlines: list[dict]) -> dict:
    owners = _owner_users(record)
    # Classification must not expose registration data through another path
    # (IR-540). Do not present a partial affiliation list as the whole record's.
    affiliations_readable = all(_reads_everything(viewer, u) for u in owners)
    facts = [_profile(u) for u in owners] if affiliations_readable else []
    return {
        "colleges": _distinct(f["college"] for f in facts) if affiliations_readable else None,
        "programs": _distinct(f["program"] for f in facts) if affiliations_readable else None,
        "author_flags": [
            {"office": office, "label": str(Party(office).label), "hint": _HINT_TEXT[office]}
            for office, field in _HINT_FIELD.items() if getattr(record, field, False)
        ],
        "researchers": [_researcher(u, viewer) for u in owners],
        "adviser": _adviser(record, viewer),
        "participants": _participants(record, viewer, owners) if readable else None,
        "due_dates": _due_dates(deadlines) if readable else None,
    }
