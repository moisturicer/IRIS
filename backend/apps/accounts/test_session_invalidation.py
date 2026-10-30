"""Account security changes enforced through real sign-in, request and refresh."""

from rest_framework_simplejwt.tokens import AccessToken, RefreshToken
from rest_framework_simplejwt.token_blacklist.models import OutstandingToken

from apps.accounts.models import Role, User
from apps.accounts.test_sessions import LOGIN, PASSWORD, REFRESH, SessionTestBase


class AccountSessionTestBase(SessionTestBase):
    def setUp(self):
        super().setUp()
        self.admin = User.objects.create_user(
            email="session-admin@cit.edu", password=PASSWORD, is_verified=True,
            role=Role.objects.get(name="RDCO"),
        )
        response = self.client.post(
            LOGIN, {"email": self.admin.email, "password": PASSWORD}, format="json",
        )
        self.assertEqual(response.status_code, 200, response.content)
        self.admin_headers = {"HTTP_AUTHORIZATION": f"Bearer {response.data['access']}"}

    def lock(self, value):
        response = self.client.patch(
            f"/api/v1/users/{self.user.pk}/lock/", {"is_locked": value},
            format="json", **self.admin_headers,
        )
        self.assertEqual(response.status_code, 200, response.content)

    def assert_refused(self, access, refresh, code):
        response = self.get_me(access=access)
        self.assertEqual(response.status_code, 401, response.content)
        self.assertEqual(response.data["code"], code)
        response = self.client.post(REFRESH, {"refresh": refresh}, format="json")
        self.assertEqual(response.status_code, 401, response.content)
        self.assertEqual(response.data["code"], code)

    def audit_events(self, event_type):
        response = self.client.get(
            "/api/v1/audit/", {"event_type": event_type}, **self.admin_headers,
        )
        self.assertEqual(response.status_code, 200, response.content)
        return response.data["results"]


class LockingEndsSessionsTests(AccountSessionTestBase):
    def test_lock_ends_all_sessions_and_unlock_does_not_revive_them(self):
        self.sign_in()
        first = self.access, self.refresh
        self.sign_in()
        second = self.access, self.refresh
        self.lock(True)
        for tokens in (first, second):
            self.assert_refused(*tokens, "account_locked")
        response = self.client.get("/api/v1/users/sessions/", **self.admin_headers)
        self.assertEqual(response.status_code, 200, response.content)
        self.assertNotIn(self.user.pk, [row["user_id"] for row in response.data])
        self.lock(False)
        for tokens in (first, second):
            self.assert_refused(*tokens, "account_locked")
        self.sign_in()
        self.assertEqual(self.get_me().status_code, 200)
        self.assertEqual(self.refresh_tokens().status_code, 200)
        for event_type in ("ACCOUNT_LOCKED", "ACCOUNT_UNLOCKED"):
            events = self.audit_events(event_type)
            self.assertEqual(len(events), 1)
            self.assertEqual(events[0]["user"], self.admin.pk)
            self.assertEqual(events[0]["metadata"], {"target_user": self.user.email})

    def test_direct_lock_is_enforced_on_requests_and_refresh(self):
        self.sign_in()
        User.objects.filter(pk=self.user.pk).update(is_locked=True)
        self.assert_refused(self.access, self.refresh, "account_locked")

    def test_deactivation_is_enforced_on_requests_and_refresh(self):
        self.sign_in()
        User.objects.filter(pk=self.user.pk).update(is_active=False)
        self.assert_refused(self.access, self.refresh, "account_locked")

    def test_a_locked_account_cannot_use_an_access_token_without_sid(self):
        self.sign_in()
        access = str(AccessToken.for_user(self.user))
        self.lock(True)
        response = self.get_me(access=access)
        self.assertEqual(response.status_code, 401, response.content)
        self.assertEqual(response.data["code"], "account_locked")

    def test_an_unrelated_accounts_tokens_still_work(self):
        self.sign_in()
        self.lock(True)
        response = self.client.get("/api/v1/users/me/", **self.admin_headers)
        self.assertEqual(response.status_code, 200, response.content)


NEW_PASSWORD = "Fresh-Kingfisher-739!"


class PasswordChangeEndsOtherSessionsTests(AccountSessionTestBase):
    def change_password(self, *, access=None, old_password=PASSWORD):
        return self.client.post(
            "/api/v1/auth/password/change/",
            {"old_password": old_password, "new_password": NEW_PASSWORD}, format="json",
            HTTP_AUTHORIZATION=f"Bearer {access or self.access}",
        )

    def test_password_change_spares_this_device_and_ends_the_other_device(self):
        self.sign_in()
        other = self.access, self.refresh
        self.sign_in()
        response = self.change_password()
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(self.get_me().status_code, 200)
        self.assertEqual(self.refresh_tokens().status_code, 200)
        self.assert_refused(*other, "session_ended_password_changed")
        response = self.client.post(
            LOGIN, {"email": self.user.email, "password": PASSWORD}, format="json",
        )
        self.assertEqual(response.status_code, 401, response.content)
        response = self.client.post(
            LOGIN, {"email": self.user.email, "password": NEW_PASSWORD}, format="json",
        )
        self.assertEqual(response.status_code, 200, response.content)
        events = self.audit_events("PASSWORD_CHANGED")
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["user"], self.user.pk)
        self.assertEqual(events[0]["metadata"], {})

    def test_wrong_old_password_ends_no_session_and_writes_no_event(self):
        self.sign_in()
        other = self.access, self.refresh
        self.sign_in()
        response = self.change_password(old_password="incorrect")
        self.assertEqual(response.status_code, 400, response.content)
        self.assertEqual(self.get_me().status_code, 200)
        self.assertEqual(self.refresh_tokens().status_code, 200)
        self.assertEqual(self.get_me(access=other[0]).status_code, 200)
        response = self.client.post(REFRESH, {"refresh": other[1]}, format="json")
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(self.audit_events("PASSWORD_CHANGED"), [])

    def test_change_without_sid_ends_every_tracked_session(self):
        self.sign_in()
        first = self.access, self.refresh
        self.sign_in()
        second = self.access, self.refresh
        response = self.change_password(access=str(AccessToken.for_user(self.user)))
        self.assertEqual(response.status_code, 200, response.content)
        for tokens in (first, second):
            self.assert_refused(*tokens, "session_ended_password_changed")

    def test_a_rotated_current_refresh_still_works_after_the_change(self):
        self.sign_in()
        other = self.access, self.refresh
        self.sign_in()
        response = self.refresh_tokens()
        self.assertEqual(response.status_code, 200, response.content)
        self.access, self.refresh = response.data["access"], response.data["refresh"]
        self.assertEqual(self.change_password().status_code, 200)
        self.assertEqual(self.get_me().status_code, 200)
        self.assertEqual(self.refresh_tokens().status_code, 200)
        self.assert_refused(*other, "session_ended_password_changed")

    def test_preexisting_stored_tokens_without_sid_keep_the_current_device_signed_in(self):
        self.sign_in()
        other = self.access, self.refresh
        self.sign_in()
        # Fixture for the stored payload before IR-646: for_user persisted it
        # before sid was added to the JWT sent to the browser. Observe only HTTP.
        for raw in (other[1], self.refresh):
            stored = RefreshToken(raw)
            del stored["sid"]
            OutstandingToken.objects.filter(jti=stored["jti"]).update(token=str(stored))
        self.assertEqual(self.change_password().status_code, 200)
        self.assertEqual(self.get_me().status_code, 200)
        self.assertEqual(self.refresh_tokens().status_code, 200)
        self.assert_refused(*other, "session_ended_password_changed")
