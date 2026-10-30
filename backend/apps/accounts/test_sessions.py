"""
A session ends after 30 minutes of inactivity, not of elapsed time (IR-166, NFR-S2).

The access token's 30-minute lifetime was never an inactivity rule: the client
refreshes silently, so a session lasted the refresh token's 7 days whether or
not anyone was at the keyboard. Now login opens a `UserSession` whose id rides
in every token (`sid`), and authentication and refresh both refuse a session
idle past the limit.

"Activity" is what the user did, not what the browser did. The client sends
`X-IRIS-Idle-Seconds` -- seconds since the last real interaction -- with every
request, so a poll from an untouched tab carries a large number and extends
nothing. A request without the header (a script, the AI stream's bare fetch)
counts as activity at the moment it arrives.

The clock moved here is `apps.accounts.sessions.now` alone. The tokens' own
expiry uses real time and stays valid, which is what isolates the idle rule:
an 8-hour test would otherwise be testing token lifetime.
"""

from datetime import timedelta
from unittest.mock import patch

from django.utils import timezone
from rest_framework.test import APITestCase
from rest_framework_simplejwt.tokens import AccessToken, RefreshToken

from apps.accounts.models import User, UserSession

LOGIN = "/api/v1/auth/login/"
LOGOUT = "/api/v1/auth/logout/"
REFRESH = "/api/v1/auth/token/refresh/"
ME = "/api/v1/users/me/"
PASSWORD = "pw12345!"


class Clock:
    def __init__(self):
        self.at = timezone.now()

    def __call__(self):
        return self.at

    def advance(self, **kwargs):
        self.at += timedelta(**kwargs)


class SessionTestBase(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email="idle@cit.edu", password=PASSWORD, first_name="Idle", last_name="User",
            is_verified=True,
        )
        self.clock = Clock()
        patcher = patch("apps.accounts.sessions.now", self.clock)
        patcher.start()
        self.addCleanup(patcher.stop)

    def sign_in(self):
        response = self.client.post(LOGIN, {"email": self.user.email, "password": PASSWORD}, format="json")
        self.assertEqual(response.status_code, 200, response.content)
        self.access, self.refresh = response.data["access"], response.data["refresh"]

    def get_me(self, idle_seconds=None, access=None):
        headers = {"HTTP_AUTHORIZATION": f"Bearer {access or self.access}"}
        if idle_seconds is not None:
            headers["HTTP_X_IRIS_IDLE_SECONDS"] = str(idle_seconds)
        return self.client.get(ME, **headers)

    def refresh_tokens(self, idle_seconds=None):
        headers = {}
        if idle_seconds is not None:
            headers["HTTP_X_IRIS_IDLE_SECONDS"] = str(idle_seconds)
        return self.client.post(REFRESH, {"refresh": self.refresh}, format="json", **headers)


class SignInOpensASessionTests(SessionTestBase):
    def test_both_tokens_carry_the_session_id(self):
        self.sign_in()
        session = UserSession.objects.get(user=self.user)
        self.assertEqual(RefreshToken(self.refresh)["sid"], str(session.id))
        self.assertEqual(AccessToken(self.access)["sid"], str(session.id))

    def test_each_sign_in_is_its_own_session(self):
        self.sign_in()
        self.sign_in()
        self.assertEqual(UserSession.objects.filter(user=self.user).count(), 2)

    def test_a_refreshed_token_keeps_the_session_id(self):
        self.sign_in()
        sid = RefreshToken(self.refresh)["sid"]
        response = self.refresh_tokens()
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(RefreshToken(response.data["refresh"])["sid"], sid)
        self.assertEqual(AccessToken(response.data["access"])["sid"], sid)


class InactivityExpiryTests(SessionTestBase):
    def test_a_session_idle_for_31_minutes_is_refused(self):
        self.sign_in()
        self.clock.advance(minutes=31)
        response = self.get_me()
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.data["code"], "session_idle")

    def test_coming_back_after_31_minutes_does_not_excuse_the_absence(self):
        # The request says "the user just clicked", and they did -- after 31
        # minutes away. The absence is what counts, not the click that ends it.
        self.sign_in()
        self.clock.advance(minutes=31)
        self.assertEqual(self.get_me(idle_seconds=0).status_code, 401)

    def test_a_session_idle_for_29_minutes_is_not(self):
        self.sign_in()
        self.clock.advance(minutes=29)
        self.assertEqual(self.get_me().status_code, 200)

    def test_an_idle_session_cannot_be_refreshed_back_to_life(self):
        self.sign_in()
        self.clock.advance(minutes=31)
        response = self.refresh_tokens()
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.data["code"], "session_idle")

    def test_once_refused_the_session_stays_ended(self):
        self.sign_in()
        self.clock.advance(minutes=31)
        self.get_me()
        self.assertIsNotNone(UserSession.objects.get(user=self.user).ended_at)
        # Fresh activity does not revive it.
        self.assertEqual(self.get_me(idle_seconds=0).status_code, 401)

    def test_eight_active_hours_are_not_expired_by_elapsed_time(self):
        self.sign_in()
        for _ in range(8 * 3):  # every 20 minutes for 8 hours
            self.clock.advance(minutes=20)
            self.assertEqual(self.get_me(idle_seconds=0).status_code, 200)

    def test_a_refresh_from_an_active_user_extends_the_session(self):
        self.sign_in()
        self.clock.advance(minutes=25)
        response = self.refresh_tokens(idle_seconds=0)
        self.assertEqual(response.status_code, 200)
        self.access, self.refresh = response.data["access"], response.data["refresh"]
        self.clock.advance(minutes=25)
        self.assertEqual(self.get_me().status_code, 200)


class BackgroundRequestsDoNotCountTests(SessionTestBase):
    def test_polling_from_an_untouched_tab_does_not_extend_the_session(self):
        self.sign_in()
        for minute in range(5, 31, 5):  # a poll every 5 minutes, nobody at the keyboard
            self.clock.advance(minutes=5)
            self.assertEqual(self.get_me(idle_seconds=minute * 60).status_code, 200)
        self.clock.advance(minutes=1)
        self.assertEqual(self.get_me(idle_seconds=31 * 60).status_code, 401)

    def test_a_background_refresh_does_not_extend_it_either(self):
        self.sign_in()
        self.clock.advance(minutes=20)
        response = self.refresh_tokens(idle_seconds=20 * 60)
        self.assertEqual(response.status_code, 200)
        self.access = response.data["access"]
        self.clock.advance(minutes=11)
        self.assertEqual(self.get_me(idle_seconds=31 * 60).status_code, 401)

    def test_a_request_without_the_header_counts_as_activity(self):
        self.sign_in()
        self.clock.advance(minutes=20)
        self.get_me()
        self.clock.advance(minutes=20)
        self.assertEqual(self.get_me().status_code, 200)

    def test_a_malformed_header_counts_as_activity(self):
        self.sign_in()
        self.clock.advance(minutes=20)
        self.assertEqual(self.get_me(idle_seconds="soon").status_code, 200)
        self.clock.advance(minutes=20)
        self.assertEqual(self.get_me().status_code, 200)

    def test_a_negative_idle_cannot_push_activity_into_the_future(self):
        self.sign_in()
        self.get_me(idle_seconds=-3600)
        self.clock.advance(minutes=31)
        self.assertEqual(self.get_me().status_code, 401)


class SessionLifecycleTests(SessionTestBase):
    def test_logout_ends_the_session(self):
        self.sign_in()
        response = self.client.post(
            LOGOUT, {"refresh": self.refresh}, format="json", HTTP_AUTHORIZATION=f"Bearer {self.access}",
        )
        self.assertEqual(response.status_code, 200)
        self.assertIsNotNone(UserSession.objects.get(user=self.user).ended_at)
        self.assertEqual(self.get_me().status_code, 401)

    def test_a_refresh_token_with_no_session_cannot_be_refreshed(self):
        # Issued before IR-166: it carries no `sid`, so it is spent rather than
        # extended, and that browser signs in again within 30 minutes.
        self.refresh = str(RefreshToken.for_user(self.user))
        self.assertEqual(self.refresh_tokens().status_code, 401)

    def test_an_access_token_with_no_session_still_authenticates(self):
        # Its own 30-minute lifetime already bounds it.
        self.assertEqual(self.get_me(access=str(AccessToken.for_user(self.user))).status_code, 200)


class RefusalSaysWhyTheSessionEndedTests(SessionTestBase):
    """A refused session's 401 names why it ended (IR-645).

    Before this every refusal said ``session_idle``, so a user who signed out
    in another tab was told they had been away too long.
    """

    def log_out(self):
        response = self.client.post(
            LOGOUT, {"refresh": self.refresh}, format="json", HTTP_AUTHORIZATION=f"Bearer {self.access}",
        )
        self.assertEqual(response.status_code, 200)

    def end_as(self, reason):
        UserSession.objects.filter(user=self.user).update(ended_at=timezone.now(), ended_reason=reason)

    def test_after_logout_the_old_access_token_is_refused_as_ended(self):
        self.sign_in()
        self.log_out()
        response = self.get_me()
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.data["code"], "session_ended")

    def test_after_logout_the_old_refresh_token_is_refused_as_ended(self):
        # The refresh token is blacklisted too; that alone would answer
        # `token_not_valid`, which says nothing about why.
        self.sign_in()
        self.log_out()
        response = self.refresh_tokens()
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.data["code"], "session_ended")

    def test_idle_expiry_is_recorded_as_idle(self):
        self.sign_in()
        self.clock.advance(minutes=31)
        self.assertEqual(self.get_me().data["code"], "session_idle")
        self.assertEqual(UserSession.objects.get(user=self.user).ended_reason, "idle")
        # Asked again, the stored reason answers the same.
        self.assertEqual(self.refresh_tokens().data["code"], "session_idle")

    def test_a_session_ended_before_reasons_were_recorded_reads_as_idle(self):
        # No backfill: whether such a session idled out or logged out cannot
        # be known, so it keeps the message it would have had before.
        self.sign_in()
        self.end_as(None)
        self.assertEqual(self.get_me().data["code"], "session_idle")
        self.assertEqual(self.refresh_tokens().data["code"], "session_idle")

    def test_a_locked_account_s_session_is_refused_as_locked(self):
        # Nothing writes this reason yet; IR-644's lock slice will.
        self.sign_in()
        self.end_as("locked")
        self.assertEqual(self.get_me().data["code"], "account_locked")
        self.assertEqual(self.refresh_tokens().data["code"], "account_locked")

    def test_a_session_ended_by_a_password_change_says_so(self):
        # Nothing writes this reason yet; IR-644's password slice will.
        self.sign_in()
        self.end_as("password_changed")
        self.assertEqual(self.get_me().data["code"], "session_ended_password_changed")
        self.assertEqual(self.refresh_tokens().data["code"], "session_ended_password_changed")
