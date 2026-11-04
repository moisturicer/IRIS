"""Opening a research session: a Django-signed grant for an owned run (IR-717).

Outcomes: 404 missing or foreign, 409 `ended`, 403 `unauthorized`,
200 `unavailable` (ADR-008) for anything else.
"""

from django.conf import settings
from django.http import Http404
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.ai.grants import config, database, issue, reads


def _owned_run(user, pk):
    from apps.ai.models import AskRun

    run = AskRun.objects.owned_by(user).filter(pk=pk).first()
    if run is None:
        raise Http404
    return run


#: Refusal -> HTTP status. Anything else answers `unavailable`.
REFUSED_STATUS = {issue.Refusal.ENDED: 409, issue.Refusal.UNAUTHORIZED: 403}
UNAVAILABLE = {"status": "unavailable"}


def _outcome(make, purpose=issue.READER_RUN):
    try:
        grant = make()
        # Never hand out a grant the verifier would refuse.
        if database.verify(grant.token, purpose) is None:
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
    body = {"status": "granted", "grant": grant.token, "expires_at": grant.expires_at.isoformat()}
    if purpose == issue.READER_RUN:
        body["run_id"] = grant.claims["run"]
    return Response(body, status=201)


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


class ReaderSessionGrantView(APIView):
    """POST /api/v1/ai/runtime/grant/ -- the signed-in reader, no run (IR-722).

    Optional `record_id` is a Paper Chat scope (IR-719); unreadable reads nothing.
    """

    permission_classes = [IsAuthenticated]

    def post(self, request):
        record_id = request.data.get("record_id")
        if record_id is not None and (
                type(record_id) is not int or record_id < 1):
            return Response({"status": "invalid"}, status=400)
        return _outcome(
            lambda: issue.reader_session_grant(request.user, record_id), issue.READER_SESSION)


class RuntimeEdgeGrantView(APIView):
    """Authenticate a same-origin nginx subrequest; no service credential leaves nginx."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        if not settings.AI_RUNTIME_READER:
            # The switch is the deployment's, so the edge refuses rather than
            # letting a browser reach the runtime on its own (IR-863).
            return Response(status=403)
        raw = request.headers.get("X-IRIS-Record")
        record_id = None
        if raw:
            if not raw.isascii() or not raw.isdigit() or len(raw) > 19:
                return Response({"status": "invalid"}, status=400)
            record_id = int(raw)
            if not 0 < record_id < 2**63:
                return Response({"status": "invalid"}, status=400)
            if not reads.research_records(request.user, scope_record_id=record_id).exists():
                raise Http404
        result = _outcome(lambda: issue.reader_session_grant(request.user, record_id), issue.READER_SESSION)
        if result.status_code != 201:
            return Response(status=403)
        return Response(status=204, headers={
            "X-IRIS-Reader-Grant": result.data["grant"], "Cache-Control": "no-store",
        })


class ReaderPathView(APIView):
    """Which path answers this deployment's Ask IRIS questions (IR-863).

    `runtime` or `django`, from `AI_RUNTIME_READER` alone: nothing the request
    carries changes it.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        path = "runtime" if settings.AI_RUNTIME_READER else "django"
        return Response({"path": path}, headers={"Cache-Control": "no-store"})
