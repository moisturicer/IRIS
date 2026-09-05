from datetime import date

from django.http import HttpResponse
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated

from core.permissions import IsOpportunityPoster

from .models import Opportunity
from .serializers import OpportunitySerializer
from .services import build_ics


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
        # Closed-and-stale items drop off for everyone, including posters: an
        # opportunity nobody can act on is noise on a deadline board.
        return Opportunity.objects.visible().select_related("posted_by")

    def get_permissions(self):
        if self.action in ("create", "update", "partial_update", "destroy"):
            return [IsAuthenticated(), IsOpportunityPoster()]
        return super().get_permissions()

    def perform_create(self, serializer):
        serializer.save(posted_by=self.request.user)

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
