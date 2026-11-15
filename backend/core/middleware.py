"""Response middleware owned by the project rather than by an app."""

from django.conf import settings
from django.utils.deprecation import MiddlewareMixin


class ContentSecurityPolicyMiddleware(MiddlewareMixin):
    """
    Add `settings.CONTENT_SECURITY_POLICY` to every response (IR-663).

    Django 5.2 has no CSP support of its own (it arrives in 6.0), and this is
    the one header `SecurityMiddleware` cannot send. While
    `CONTENT_SECURITY_POLICY_REPORT_ONLY` is true the policy goes out as
    `Content-Security-Policy-Report-Only`, which a browser reports and does not
    enforce. An empty policy sends nothing. A view that set its own policy keeps
    it.

    `MiddlewareMixin`, like Django's own security middleware, so it runs
    natively under ASGI and adds no thread hop to Ask IRIS's streaming views.
    """

    def process_response(self, request, response):
        policy = settings.CONTENT_SECURITY_POLICY
        if policy:
            name = (
                "Content-Security-Policy-Report-Only"
                if settings.CONTENT_SECURITY_POLICY_REPORT_ONLY
                else "Content-Security-Policy"
            )
            response.headers.setdefault(name, policy)
        return response


class ApiResponseHeadersMiddleware(MiddlewareMixin):
    """
    Keep API responses out of browser caches and out of browser tabs (IR-821).

    Every response Django serves under `/api/` gets `Cache-Control: no-store`
    (ASVS 8.2.1),
    so a record, a review or a person's details is never left in a shared
    computer's cache. Public endpoints get it too: one rule is easier to keep
    than a list of what is safe to cache, and the app's own data layer does the
    caching it needs in memory.

    JSON responses also get `Content-Disposition: attachment; filename="api.json"`
    (ASVS 14.4.2; the decision is recorded in docs/testing/SECURITY_CHECKLIST.md).
    The AI runtime's replies under `/api/v1/ai/runtime/` never pass through
    Django: nginx sends them `no-store` (runtime-edge.conf), not this filename. A browser then never
    renders an API response as a page, even if a future content type would let
    it. The app's own fetch calls ignore the header; an API address opened
    directly in a tab downloads instead of displaying.

    A view that sets its own `Cache-Control` or `Content-Disposition` keeps it:
    that is how a view opts out, as the profile photo (cached privately for a
    day) and the downloads (their own filename) do.
    """

    def process_response(self, request, response):
        if not request.path.startswith("/api/"):
            return response
        response.headers.setdefault("Cache-Control", "no-store")
        content_type = response.headers.get("Content-Type", "")
        if content_type.split(";", 1)[0].strip() == "application/json":
            response.headers.setdefault("Content-Disposition", 'attachment; filename="api.json"')
        return response
