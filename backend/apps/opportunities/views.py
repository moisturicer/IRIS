from django.db import transaction
from django.http import Http404, HttpResponse
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from core.enums import CallStatus
from core.permissions import IsCallModerator, IsOpportunityPoster, is_call_moderator

from . import review
from .models import Opportunity
from .serializers import DecisionSerializer, OpportunitySerializer, ReasonSerializer, RejectionSerializer
from .services import build_ics


NEEDS_REASON = "An Adviser posted this Call. Remove it with a reason, which they receive."
NEEDS_NO_REASON = "This Call needs no reason. Delete it instead."
NOT_WAITING = "This Call isn't waiting for RDCO any more."
CHANGED_SINCE_SEEN = "This Call changed since you opened it. Open it again to see what changed."


class OpportunityViewSet(viewsets.ModelViewSet):
    """
    Browse is open to any authenticated user; publishing is not.

    NOTE on get_permissions: this returns `super().get_permissions()` as the
    fallback rather than a hardcoded `[IsAuthenticated()]`. That distinction is
    not cosmetic -- IR-120 found six endpoints in this codebase whose declared
    permissions were silently dropped because a hardcoded fallback swallowed the
    class-level `permission_classes`. Tests below pin the behaviour of every
    action rather than trusting this method to be read correctly.
    """
    serializer_class   = OpportunitySerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        # Only what this viewer may open (ADR-050 decision 8): a Call waiting
        # for RDCO, or rejected, is filtered out for anyone but its poster and
        # RDCO, so it answers exactly like a missing Call.
        #
        # The board lists only confirmed Calls that aren't Over (decision 7),
        # for everyone, posters included. Detail, edit, delete and the
        # calendar still reach an Over Call, so a poster can fix a mistyped
        # date that ended it (owner, 2026-11-15).
        calls = (
            Opportunity.objects.visible_to(self.request.user)
            .select_related("posted_by__role").prefetch_related("areas")
        )
        if self.action == "list":
            return calls.on_board()
        if self.action in ("update", "partial_update"):
            # An edit holds the row for its whole transaction (see `update`).
            # Only the Call's own row: Postgres can't lock a missing poster.
            return calls.select_for_update(of=("self",))
        if self.action == "calendar":
            # Like the board, the calendar serves confirmed Calls only. Filtered
            # here, not checked after lookup, so a waiting Call's 404 is the very
            # same response as a missing one's.
            return calls.filter(status=CallStatus.CONFIRMED)
        return calls

    def get_permissions(self):
        if self.action in ("create", "update", "partial_update", "destroy"):
            return [IsAuthenticated(), IsOpportunityPoster()]
        return super().get_permissions()

    def list(self, request, *args, **kwargs):
        """
        The page, plus whether this viewer may post (IR-530).

        `can_post` sits beside the results rather than in a separate endpoint so
        the board learns it from the request it already makes. It is decided by
        `IsOpportunityPoster.has_permission`, the same check `create` runs, so
        the button and the endpoint cannot disagree.
        """
        response = super().list(request, *args, **kwargs)
        response.data["can_post"] = IsOpportunityPoster().has_permission(request, self)
        # Whether this viewer works RDCO's Call Requests queue (IR-762).
        response.data["can_review_requests"] = is_call_moderator(request.user)
        return response

    def _page(self, calls):
        page = self.paginate_queryset(calls)
        return self.get_paginated_response(self.get_serializer(page, many=True).data)

    @action(detail=False, methods=["get"], permission_classes=[IsAuthenticated, IsCallModerator])
    def requests(self, request):
        """
        RDCO's queue (ADR-050 decision 8): Calls waiting for confirmation,
        oldest first. A request whose paper deadline has passed leaves it at
        once, before the daily job deletes it (decision 9, as amended).
        """
        return self._page(self.get_queryset().waiting().order_by("created_at", "id"))

    @action(detail=False, methods=["get"], permission_classes=[IsAuthenticated, IsOpportunityPoster])
    def mine(self, request):
        """
        The viewer's own Calls in every status, Over ones included, so an
        Adviser can see where each request stands and read a rejection's reason.
        """
        return self._page(self.get_queryset().filter(posted_by=request.user))

    def _decided(self, act, body_class):
        """
        Run one of RDCO's decisions. The body names the version RDCO saw
        (`updated_at`), so a decision on a Call decided, lapsed or edited since
        it was opened is refused with 409, which IR-765 shows as the server's
        refusal rather than pretending it worked.
        """
        call = self.get_object()
        body = body_class(data=self.request.data)
        body.is_valid(raise_exception=True)
        try:
            act(call.pk, by=self.request.user, seen=body.validated_data.pop("updated_at"),
                **body.validated_data)
        except Opportunity.DoesNotExist:
            raise Http404
        except review.NotWaiting:
            return Response({"detail": NOT_WAITING}, status=status.HTTP_409_CONFLICT)
        except review.ChangedSinceSeen:
            return Response({"detail": CHANGED_SINCE_SEEN}, status=status.HTTP_409_CONFLICT)
        return Response(self.get_serializer(self.get_queryset().get(pk=call.pk)).data)

    @action(detail=True, methods=["post"], permission_classes=[IsAuthenticated, IsCallModerator])
    def confirm(self, request, pk=None):
        """RDCO puts an Adviser's request on the board (decision 8)."""
        return self._decided(review.confirm, DecisionSerializer)

    @action(detail=True, methods=["post"], permission_classes=[IsAuthenticated, IsCallModerator])
    def reject(self, request, pk=None):
        """RDCO turns a request down, with a reason the Adviser receives (decision 8)."""
        return self._decided(review.reject, RejectionSerializer)

    @action(detail=True, methods=["post"], permission_classes=[IsAuthenticated, IsCallModerator])
    def remove(self, request, pk=None):
        """
        RDCO deletes an Adviser's Call with a reason they receive (decision 11).
        A Call that needs no reason is deleted with DELETE instead, so each
        case has one way in, matching `can_remove` and `can_delete`.
        """
        call = self.get_object()
        if not call.posted_by_adviser():
            return Response({"detail": NEEDS_NO_REASON}, status=status.HTTP_400_BAD_REQUEST)
        reason = ReasonSerializer(data=request.data)
        reason.is_valid(raise_exception=True)
        try:
            review.remove(call.pk, by=request.user, reason=reason.validated_data["reason"])
        except Opportunity.DoesNotExist:
            raise Http404
        return Response(status=status.HTTP_204_NO_CONTENT)

    def destroy(self, request, *args, **kwargs):
        """
        A poster deletes their own Call in any status, and RDCO deletes its
        own or a colleague's. An Adviser's Call, deleted by RDCO, needs a
        reason, so it goes through `remove` instead (decision 11).
        """
        call = self.get_object()
        if call.posted_by_id != request.user.pk and call.posted_by_adviser():
            return Response({"detail": NEEDS_REASON}, status=status.HTTP_400_BAD_REQUEST)
        return super().destroy(request, *args, **kwargs)

    def update(self, request, *args, **kwargs):
        """
        One transaction per edit, holding the Call's row (see `get_queryset`),
        so a concurrent confirm, reject or lapse can't be overwritten by a save
        that read the row before it, and the job, which skips locked rows,
        can't delete a Call mid-edit. Any notice goes out after the commit.
        """
        with transaction.atomic():
            return super().update(request, *args, **kwargs)

    def perform_update(self, serializer):
        """
        An Adviser's edit to a confirmed or rejected Call sends it back to
        RDCO (decisions 8 and 10). A request that changes nothing is not an
        edit. RDCO's own edits never change a Call's status.
        """
        call = serializer.instance
        if (
            not is_call_moderator(self.request.user)
            and call.status != CallStatus.PENDING
            and review.changes_anything(call, serializer.validated_data)
        ):
            review.returned_for_review(call)
        serializer.save()

    def perform_create(self, serializer):
        # RDCO's Calls go public at once; an Adviser's wait for RDCO (decision 8).
        if is_call_moderator(self.request.user):
            serializer.save(posted_by=self.request.user, status=CallStatus.CONFIRMED)
            return
        call = serializer.save(posted_by=self.request.user, status=CallStatus.PENDING)
        review.submitted(call)

    @action(detail=True, methods=["get"])
    def calendar(self, request, pk=None):
        """
        The deadline as a .ics file, for the user's own calendar.

        Deliberately not an in-app scheduled reminder: those need Celery to
        consume its own queue, which it currently does not (IR-83), so they
        would silently never fire. A calendar file that the user's own client
        owns cannot fail quietly in that way.
        """
        opportunity = self.get_object()
        response = HttpResponse(build_ics(opportunity), content_type="text/calendar; charset=utf-8")
        response["Content-Disposition"] = f'attachment; filename="opportunity-{opportunity.pk}.ics"'
        return response
