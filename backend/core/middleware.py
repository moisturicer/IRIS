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
        policy = getattr(settings, "CONTENT_SECURITY_POLICY", "")
        if policy:
            name = (
                "Content-Security-Policy-Report-Only"
                if getattr(settings, "CONTENT_SECURITY_POLICY_REPORT_ONLY", True)
                else "Content-Security-Policy"
            )
            response.headers.setdefault(name, policy)
        return response
