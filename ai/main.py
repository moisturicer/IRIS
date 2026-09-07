"""IRIS AI Gateway (ADR-014, ADR-017).

Two of ADR-014's five preconditions are enforced in this file, and both are
absences rather than features (IR-156):

**No CORS.** There used to be a `CORSMiddleware` here allowing
`http://localhost:5173` with `allow_credentials=True`. A browser is not a
client of this service — Django is. CORS exists to let a browser call an
origin it did not come from, so configuring it here states the opposite of the
architecture, and `allow_credentials` with a wildcard method/header set is how
a service reachable from a page becomes a service *used* by one.

**No unauthenticated request is served.** Every request must carry the shared
service secret. This is the whole of the gateway's authentication: it holds a
provider API key, and an unauthenticated service holding a vendor credential is
not a partial deployment — ADR-014 says there is no middle state.

The gateway also publishes no port (see both Compose files) so it is reachable
only on the Compose network. Auth is not a substitute for that; it is the
second layer, for when the first is misconfigured.
"""

import hmac

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from ai.infrastructure.settings import settings

app = FastAPI(
    title="IRIS AI Gateway",
    description="FastAPI async gateway for LLM and Vector Search in IRIS",
    version="1.0.0",
)

#: Paths served without the service secret. Deliberately only the health check:
#: Compose needs it before any secret is exchanged, and it reveals nothing but
#: liveness. `/` is NOT here -- an unauthenticated root that names the service
#: is free reconnaissance for anything that reaches the network.
PUBLIC_PATHS = frozenset({"/health"})

SERVICE_HEADER = "x-iris-service-secret"


@app.middleware("http")
async def require_service_secret(request: Request, call_next):
    """Reject any request that does not present the shared service secret.

    `hmac.compare_digest` rather than `==`: the comparison is against a secret,
    and a short-circuiting comparison leaks its prefix through timing. The cost
    of getting this right is one import.

    A missing *configured* secret fails closed. Starting the gateway with no
    secret and serving everything would be the exact deployment ADR-014 refuses,
    and it would look healthy while doing it.
    """
    if request.url.path in PUBLIC_PATHS:
        return await call_next(request)

    expected = settings.SERVICE_SECRET
    if not expected:
        return JSONResponse(
            status_code=503,
            content={"detail": "Gateway is not configured with a service secret."},
        )

    presented = request.headers.get(SERVICE_HEADER, "")
    if not presented or not hmac.compare_digest(presented, expected):
        return JSONResponse(status_code=401, content={"detail": "Unauthorized."})

    return await call_next(request)


@app.get("/health")
async def health_check():
    """Healthcheck endpoint for Docker Compose. Unauthenticated by design."""
    return {"status": "healthy", "service": "ai-gateway"}


@app.get("/")
async def root():
    return {"message": "Welcome to IRIS AI Gateway"}


from ai.api.chat import router as chat_router  # noqa: E402  (router import after app)

app.include_router(chat_router, prefix="/api/v1/ai", tags=["ai"])
