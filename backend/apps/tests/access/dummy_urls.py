"""
A URLconf with one route nobody declared, for `test_access_matrix` (IR-615).

The real URLconf plus a route two `include()`s deep, so the test proves the
walk recurses rather than reading only the top level. Selected with
`override_settings(ROOT_URLCONF=...)`; nothing else imports it.
"""

from django.http import HttpResponse
from django.urls import include, path

from config.urls import urlpatterns as real_urlpatterns


def preview(request, pk):
    """The ticket's example: a preview route shipped with no access rule."""
    return HttpResponse(b"a file anyone can read")


nested = [path("files/<int:pk>/preview/", preview, name="matrix-undeclared-preview")]

urlpatterns = real_urlpatterns + [
    path("api/v1/documents/", include([path("", include(nested))])),
]
