"""Opening a research session: a Django-signed grant for an owned run (IR-717).

Public outcomes carry a status code and nothing else: 404 for a run that is
missing or someone else's, 409 `ended`, 403 `unauthorized` for a renewal the
verifier refuses, and 200 `unavailable` when grants are off or cannot verify
-- the same explicit unavailable state Ask IRIS answers with (ADR-008).
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


def _outcome(make):
    try:
        grant = make()
        # Never hand out a grant the verifier would refuse.
        if database.verify(grant.token, issue.READER_RUN) is None:
            raise config.GrantsUnavailable
    except config.GrantsUnavailable:
        return Response({"status": "unavailable"}, status=200)
    except issue.GrantRefused as refused:
        if refused.code == "not_found":
            raise Http404
        status = {"ended": 409, "unauthorized": 403}[refused.code]
        return Response({"status": refused.code}, status=status)
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
