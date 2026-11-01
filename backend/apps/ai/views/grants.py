"""Opening a research session: a Django-signed grant for an owned run (IR-717).

Outcomes: 404 missing or foreign, 409 `ended`, 403 `unauthorized`,
200 `unavailable` (ADR-008) for anything else.
"""

from django.http import Http404
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.ai.grants import config, database, issue


def _owned_run(user, pk):
    from apps.ai.models import AskRun

    run = AskRun.objects.owned_by(user).filter(pk=pk).first()
    if run is None:
        raise Http404
    return run


#: Refusal -> HTTP status. Anything else answers `unavailable`.
REFUSED_STATUS = {issue.Refusal.ENDED: 409, issue.Refusal.UNAUTHORIZED: 403}
UNAVAILABLE = {"status": "unavailable"}


def _outcome(make):
    try:
        grant = make()
        # Never hand out a grant the verifier would refuse.
        if database.verify(grant.token, issue.READER_RUN) is None:
            raise config.GrantsUnavailable
    except config.GrantsUnavailable:
        return Response(UNAVAILABLE, status=200)
    except issue.GrantRefused as refused:
        if refused.code == issue.Refusal.NOT_FOUND:
            raise Http404
        status = REFUSED_STATUS.get(refused.code)
        if status is None:
            return Response(UNAVAILABLE, status=200)
        return Response({"status": issue.Refusal(refused.code).value}, status=status)
    return Response({
        "status": "granted", "run_id": grant.claims["run"], "grant": grant.token,
        "expires_at": grant.expires_at.isoformat(),
    }, status=201)


class RunGrantView(APIView):
    """POST /api/v1/ai/ask/runs/<uuid>/grant/ -- the asker's own run only."""

    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        run = _owned_run(request.user, pk)
        return _outcome(lambda: issue.reader_grant(request.user, run))


class RunGrantRenewView(APIView):
    """POST /api/v1/ai/ask/runs/<uuid>/grant/renew/ with {"grant": ...}."""

    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        run = _owned_run(request.user, pk)
        token = request.data.get("grant")
        if not isinstance(token, str) or not token:
            return Response({"status": "invalid"}, status=400)
        return _outcome(lambda: issue.renew_reader_grant(request.user, run, token))
