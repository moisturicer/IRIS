"""
IR-821: API responses stay out of browser caches and out of browser tabs.

`core.middleware.ApiResponseHeadersMiddleware` sends `Cache-Control: no-store`
on every `/api/` response (ASVS 8.2.1) and `Content-Disposition: attachment;
filename="api.json"` on JSON ones (ASVS 14.4.2). A view that sets either header
itself keeps its own. Paths outside `/api/` are left alone.
"""

import pytest
from django.http import HttpResponse, JsonResponse
from django.test import RequestFactory, SimpleTestCase
from rest_framework.test import APIClient

from core.middleware import ApiResponseHeadersMiddleware

JSON_DISPOSITION = 'attachment; filename="api.json"'


def _through(path, response):
    request = RequestFactory().get(path)
    return ApiResponseHeadersMiddleware(lambda _request: response)(request)


class MiddlewareTests(SimpleTestCase):

    def test_an_api_json_response_is_never_stored_and_never_rendered(self):
        response = _through("/api/v1/records/", JsonResponse({"ok": True}))
        self.assertEqual(response["Cache-Control"], "no-store")
        self.assertEqual(response["Content-Disposition"], JSON_DISPOSITION)

    def test_a_refusal_gets_the_same_headers(self):
        response = _through("/api/v1/records/9/", JsonResponse({"detail": "Not found."}, status=404))
        self.assertEqual(response["Cache-Control"], "no-store")
        self.assertEqual(response["Content-Disposition"], JSON_DISPOSITION)

    def test_a_view_that_sets_its_own_cache_control_keeps_it(self):
        own = JsonResponse({})
        own["Cache-Control"] = "private, max-age=86400"
        self.assertEqual(_through("/api/v1/users/me/photo/", own)["Cache-Control"], "private, max-age=86400")

    def test_a_download_keeps_its_own_filename(self):
        pdf = HttpResponse(b"%PDF-", content_type="application/pdf")
        pdf["Content-Disposition"] = 'attachment; filename="paper.pdf"'
        response = _through("/api/v1/records/3/download/", pdf)
        self.assertEqual(response["Content-Disposition"], 'attachment; filename="paper.pdf"')
        self.assertEqual(response["Cache-Control"], "no-store")

    def test_only_json_is_named_api_json(self):
        for response in (
            HttpResponse("a,b", content_type="text/csv; charset=utf-8"),
            HttpResponse("data: x\n\n", content_type="text/event-stream"),
            HttpResponse(b"%PDF-", content_type="application/pdf"),
        ):
            self.assertFalse(_through("/api/v1/x/", response).has_header("Content-Disposition"))

    def test_json_with_a_charset_is_still_json(self):
        response = _through("/api/v1/x/", HttpResponse("{}", content_type="application/json; charset=utf-8"))
        self.assertEqual(response["Content-Disposition"], JSON_DISPOSITION)

    def test_paths_outside_the_api_are_left_alone(self):
        for path in ("/django-admin/login/", "/static/admin/css/base.css", "/apiary/"):
            response = _through(path, JsonResponse({}))
            self.assertFalse(response.has_header("Cache-Control"), path)
            self.assertFalse(response.has_header("Content-Disposition"), path)


@pytest.mark.django_db
def test_the_real_stack_sends_them_on_public_and_signed_in_answers(django_user_model):
    client = APIClient()
    public = client.get("/api/v1/colleges/")
    assert public.status_code == 200
    assert public["Cache-Control"] == "no-store"
    assert public["Content-Disposition"] == JSON_DISPOSITION

    user = django_user_model.objects.create_user(
        email="ir821@iris.test", password="x" * 16, first_name="Ir", last_name="Eight", is_verified=True, consent_given=True,
    )
    client.force_authenticate(user)
    signed_in = client.get("/api/v1/notifications/")
    assert signed_in["Cache-Control"] == "no-store"
    assert signed_in["Content-Disposition"] == JSON_DISPOSITION
