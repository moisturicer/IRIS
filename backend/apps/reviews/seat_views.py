"""
The seat endpoints (ADR-032 §4, IR-415). Mounted at `/api/v1/`.

    POST assignments/<id>/claim/         an office member takes it from the pool
    POST assignments/<id>/assign/        {"reviewer": id}  a coordinator seats a member
    POST assignments/<id>/add-reviewer/  {"reviewer": id}  a seat holder adds a colleague
    POST seats/<id>/open/                the holder opens their review
    POST seats/<id>/reassign/            {"reviewer": id}  a coordinator moves a seat
    POST seats/<id>/withdraw/            a coordinator takes a seat away

Nomination has no endpoint: it happens inside routing (IR-261), which calls
`seats.nominate()`.

**Refusals follow ADR-022 §Amendment 4**, as the document-request endpoints
do: **404** when the assignment or seat does not exist or is on a Record the
caller cannot see (`visible_to()`, IR-153); **403** when they can see it but
the act's predicate refuses them; **400** when the act is understood but not
possible now (a closed assignment, a reviewer from another office, a seat
already held).
"""

from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.records.models import Record

from . import seats
from .models import RecordAssignment, ReviewerSeat


def _not_found():
    return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)


def _visible_assignment(pk, user):
    return (
        RecordAssignment.objects.filter(pk=pk, record__in=Record.objects.visible_to(user))
        .select_related("record")
        .first()
    )


def _visible_seat(pk, user):
    return (
        ReviewerSeat.objects.filter(
            pk=pk, assignment__record__in=Record.objects.visible_to(user)
        )
        .select_related("assignment__record", "reviewer")
        .first()
    )


def _reviewer_from(request):
    """`(user, None)` for the body's `reviewer`, else `(None, a 400)`."""
    raw = request.data.get("reviewer")
    try:
        pk = int(raw)
    except (TypeError, ValueError):
        return None, Response(
            {"detail": "Name the reviewer: `reviewer` is a user id."},
            status=status.HTTP_400_BAD_REQUEST,
        )
    reviewer = get_user_model().objects.filter(pk=pk, is_active=True).first()
    if reviewer is None:
        return None, Response(
            {"detail": "No such reviewer."}, status=status.HTTP_400_BAD_REQUEST
        )
    return reviewer, None


def _coordinator_refusal(user, party):
    """A 403 for anyone but a coordinator of `party`, else None."""
    try:
        seats.require_coordinator(user, party)
    except seats.SeatRefused as exc:
        return Response({"detail": str(exc)}, status=status.HTTP_403_FORBIDDEN)
    return None


def _run(act, *, created=False):
    """Run a seat act and answer with the seat it returns, or its refusal."""
    try:
        seat = act()
    except seats.SeatRefused as exc:
        return Response({"detail": str(exc)}, status=status.HTTP_403_FORBIDDEN)
    except seats.SeatError as exc:
        return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
    seat = ReviewerSeat.objects.select_related("assignment", "reviewer").get(pk=seat.pk)
    return Response(
        seats.seat_payload(seat),
        status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
    )


class ClaimView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        assignment = _visible_assignment(pk, request.user)
        if assignment is None:
            return _not_found()
        return _run(lambda: seats.claim(assignment, request.user), created=True)


class AssignView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        assignment = _visible_assignment(pk, request.user)
        if assignment is None:
            return _not_found()
        # Who may assign comes before whom they named: a non-coordinator is a
        # 403 whatever the body says.
        refused = _coordinator_refusal(request.user, assignment.party)
        if refused:
            return refused
        reviewer, refused = _reviewer_from(request)
        if refused:
            return refused
        return _run(lambda: seats.assign(assignment, request.user, reviewer), created=True)


class AddReviewerView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        assignment = _visible_assignment(pk, request.user)
        if assignment is None:
            return _not_found()
        reviewer, refused = _reviewer_from(request)
        if refused:
            return refused
        return _run(lambda: seats.add_reviewer(assignment, request.user, reviewer), created=True)


class OpenReviewView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        seat = _visible_seat(pk, request.user)
        if seat is None:
            return _not_found()
        return _run(lambda: seats.open_review(seat, request.user))


class ReassignView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        seat = _visible_seat(pk, request.user)
        if seat is None:
            return _not_found()
        refused = _coordinator_refusal(request.user, seat.assignment.party)
        if refused:
            return refused
        reviewer, refused = _reviewer_from(request)
        if refused:
            return refused
        return _run(lambda: seats.reassign(seat, request.user, reviewer), created=True)


class WithdrawView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        seat = _visible_seat(pk, request.user)
        if seat is None:
            return _not_found()
        return _run(lambda: seats.withdraw(seat, request.user))
