"""
ADR-072 (IR-1222): the refresh token lives in an HttpOnly cookie, and "Keep me
signed in" makes a session last 30 days from sign-in outside the idle rule.

**Seam: the API**, as a browser uses it. Session time comes from the patched
clock in `SessionTestBase`, so 30 days pass without waiting.
"""
from datetime import timedelta

from django.conf import settings
from django.test import override_settings
from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken, OutstandingToken
from rest_framework_simplejwt.tokens import RefreshToken

from apps.accounts.models import UserSession
from apps.accounts.test_sessions import LOGIN, PASSWORD, SessionTestBase
from apps.accounts.testing_auth import post_logout, post_refresh, refresh_from

COOKIE = settings.REFRESH_COOKIE_NAME


class CookieTestBase(SessionTestBase):
    def sign_in(self, remember=None):
        body = {"email": self.user.email, "password": PASSWORD}
        if remember is not None:
            body["remember"] = remember
        response = self.client.post(LOGIN, body, format="json")
        self.assertEqual(response.status_code, 200, response.content)
        self.login_response = response
        self.access, self.refresh = response.data["access"], refresh_from(response)
        return response


class TheTokenIsOnlyInTheCookieTests(CookieTestBase):
    def test_login_sets_an_httponly_strict_cookie_scoped_to_the_auth_endpoints(self):
        cookie = self.sign_in().cookies[COOKIE]
        self.assertTrue(cookie["httponly"])
        self.assertEqual(cookie["samesite"], "Strict")
        self.assertEqual(cookie["path"], "/api/v1/auth/")

    def test_no_response_body_carries_a_refresh_token(self):
        response = self.sign_in()
        self.assertNotIn("refresh", response.data)
        refreshed = post_refresh(self.refresh)
        self.assertEqual(refreshed.status_code, 200, refreshed.content)
        self.assertNotIn("refresh", refreshed.data)

    def test_refresh_rotates_the_cookie(self):
        self.sign_in()
        response = post_refresh(self.refresh)
        rotated = refresh_from(response)
        self.assertNotEqual(rotated, self.refresh)
        # The presented token is blacklisted now, so it is read without verifying.
        self.assertEqual(RefreshToken(rotated)["sid"], RefreshToken(self.refresh, verify=False)["sid"])

    def test_a_body_token_is_ignored(self):
        self.sign_in()
        client = self.client_class()  # Holds no cookie: the token is only in the body
        response = client.post(
            "/api/v1/auth/token/refresh/", {"refresh": self.refresh}, format="json", HTTP_X_IRIS_AUTH="1",
        )
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.data["code"], "no_session")


class NoSessionIsNotAnEndedSessionTests(CookieTestBase):
    def test_refresh_with_no_cookie_answers_no_session(self):
        response = post_refresh(None)
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.data["code"], "no_session")

    def test_a_refused_refresh_clears_the_cookie(self):
        self.sign_in()
        self.clock.advance(minutes=31)
        response = post_refresh(self.refresh)
        self.assertEqual(response.data["code"], "session_idle")
        self.assertEqual(response.cookies[COOKIE].value, "")
        self.assertEqual(response.cookies[COOKIE]["max-age"], 0)


class OnlyIRISItselfCanRefreshTests(CookieTestBase):
    def test_refresh_without_the_header_is_refused(self):
        self.sign_in()
        client = self.client_class()
        client.cookies[COOKIE] = self.refresh
        response = client.post("/api/v1/auth/token/refresh/", format="json")
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.data["detail"].code, "not_first_party")

    @override_settings(CORS_ALLOWED_ORIGINS=["https://iris.example"])
    def test_refresh_from_another_origin_is_refused(self):
        self.sign_in()
        response = post_refresh(self.refresh, HTTP_ORIGIN="https://evil.example")
        self.assertEqual(response.status_code, 403)

    @override_settings(CORS_ALLOWED_ORIGINS=["https://iris.example"])
    def test_refresh_from_an_allowed_origin_works(self):
        self.sign_in()
        response = post_refresh(self.refresh, HTTP_ORIGIN="https://iris.example")
        self.assertEqual(response.status_code, 200, response.content)

    def test_refresh_from_the_sites_own_origin_works(self):
        self.sign_in()
        response = post_refresh(self.refresh, HTTP_ORIGIN="http://testserver")
        self.assertEqual(response.status_code, 200, response.content)

    def test_logout_without_the_header_is_refused(self):
        self.sign_in()
        response = self.client.post("/api/v1/auth/logout/", format="json", HTTP_AUTHORIZATION=f"Bearer {self.access}")
        self.assertEqual(response.status_code, 403)
        self.assertIsNone(UserSession.objects.get(user=self.user).ended_at)


class LogoutTests(CookieTestBase):
    def test_logout_ends_the_session_blacklists_the_cookie_and_clears_it(self):
        self.sign_in()
        response = post_logout(self.refresh, self.access)
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.cookies[COOKIE].value, "")
        self.assertIsNotNone(UserSession.objects.get(user=self.user).ended_at)
        jti = RefreshToken(self.refresh, verify=False)["jti"]
        self.assertTrue(BlacklistedToken.objects.filter(token__jti=jti).exists())


class WithoutTheBoxTests(CookieTestBase):
    def test_the_cookie_ends_with_the_browser_and_the_session_is_not_remembered(self):
        response = self.sign_in()
        self.assertEqual(response.cookies[COOKIE]["max-age"], "")
        self.assertFalse(response.data["remembered"])
        session = UserSession.objects.get(user=self.user)
        self.assertFalse(session.remembered)
        self.assertIsNone(session.expires_at)

    def test_only_a_json_true_ticks_the_box(self):
        self.sign_in(remember="true")
        self.assertFalse(UserSession.objects.get(user=self.user).remembered)

    def test_the_idle_rule_still_ends_it(self):
        self.sign_in(remember=False)
        self.clock.advance(minutes=31)
        self.assertEqual(post_refresh(self.refresh).data["code"], "session_idle")


class KeepMeSignedInTests(CookieTestBase):
    def test_a_remembered_session_lasts_30_days_from_sign_in(self):
        response = self.sign_in(remember=True)
        self.assertTrue(response.data["remembered"])
        session = UserSession.objects.get(user=self.user)
        self.assertTrue(session.remembered)
        self.assertEqual(session.expires_at, session.created_at + timedelta(days=30))
        self.assertEqual(response.cookies[COOKIE]["max-age"], 30 * 24 * 60 * 60)

    def test_the_idle_rule_does_not_end_it(self):
        self.sign_in(remember=True)
        self.clock.advance(days=3)
        response = post_refresh(self.refresh, HTTP_X_IRIS_IDLE_SECONDS=str(3 * 24 * 60 * 60))
        self.assertEqual(response.status_code, 200, response.content)
        self.assertTrue(response.data["remembered"])

    def test_it_ends_30_days_after_sign_in_however_much_it_was_used(self):
        self.sign_in(remember=True)
        for _ in range(29):
            self.clock.advance(days=1)
            response = post_refresh(self.refresh, HTTP_X_IRIS_IDLE_SECONDS="0")
            self.assertEqual(response.status_code, 200, response.content)
            self.refresh = refresh_from(response)
        self.clock.advance(days=1)
        response = post_refresh(self.refresh)
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.data["code"], "session_expired")
        self.assertEqual(response.cookies[COOKIE].value, "")
        # Refresh refuses inside its transaction, as the idle rule does, so the
        # ending is recorded by the next authenticated request.
        me = self.get_me()
        self.assertEqual(me.status_code, 401)
        self.assertEqual(me.data["code"], "session_expired")
        self.assertEqual(UserSession.objects.get(user=self.user).ended_reason, "remembered_expired")

    def test_a_rotated_token_and_its_cookie_keep_the_sessions_end(self):
        self.sign_in(remember=True)
        session = UserSession.objects.get(user=self.user)
        self.clock.advance(days=10)
        response = post_refresh(self.refresh)
        rotated = RefreshToken(refresh_from(response))
        self.assertEqual(rotated["exp"], int(session.expires_at.timestamp()))
        self.assertEqual(response.cookies[COOKIE]["max-age"], 20 * 24 * 60 * 60)
        stored = OutstandingToken.objects.get(jti=rotated["jti"])
        self.assertEqual(stored.expires_at, session.expires_at)
