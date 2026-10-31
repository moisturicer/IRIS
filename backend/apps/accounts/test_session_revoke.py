"""
IR-657: an administrator revoking a session ends it, access token included.

`DELETE /users/sessions/<jti>/` blacklisted the refresh token and left the
tracked `UserSession` open, so the access token already issued kept working for
up to 30 minutes. Revoking now ends the session, which every token carrying its
`sid` is checked against on its next use.

**Seam: real sign-in, the real revoke endpoint, and the tokens sign-in returned.**
"""

from rest_framework_simplejwt.tokens import RefreshToken

from apps.accounts.test_session_invalidation import AccountSessionTestBase
from apps.accounts.test_sessions import REFRESH

REVOKED = "session_ended_revoked"


class RevokingEndsTheSessionTests(AccountSessionTestBase):

    def revoke(self, refresh):
        return self.client.delete(
            f"/api/v1/users/sessions/{RefreshToken(refresh)['jti']}/", **self.admin_headers,
        )

    def test_the_access_and_refresh_tokens_stop_working_at_once(self):
        self.sign_in()
        self.assertEqual(self.get_me().status_code, 200)

        response = self.revoke(self.refresh)

        self.assertEqual(response.status_code, 200, response.content)
        self.assert_refused(self.access, self.refresh, REVOKED)

    def test_signing_in_again_works(self):
        self.sign_in()
        self.revoke(self.refresh)

        self.sign_in()

        self.assertEqual(self.get_me().status_code, 200)
        self.assertEqual(self.refresh_tokens().status_code, 200)

    def test_only_that_session_ends(self):
        self.sign_in()
        first = self.access, self.refresh
        self.sign_in()

        self.revoke(first[1])

        self.assert_refused(*first, REVOKED)
        self.assertEqual(self.get_me().status_code, 200)
        self.assertEqual(self.refresh_tokens().status_code, 200)

    def test_a_token_from_after_a_refresh_is_revoked_the_same_way(self):
        self.sign_in()
        response = self.refresh_tokens()
        self.assertEqual(response.status_code, 200)
        self.access = response.data["access"]
        self.refresh = response.data.get("refresh", self.refresh)

        self.revoke(self.refresh)

        self.assert_refused(self.access, self.refresh, REVOKED)

    def test_the_active_sessions_list_stops_showing_it(self):
        self.sign_in()
        jti = RefreshToken(self.refresh)["jti"]

        self.revoke(self.refresh)

        response = self.client.get("/api/v1/users/sessions/", **self.admin_headers)
        self.assertNotIn(jti, [row["jti"] for row in response.data])

    def test_the_audit_event_names_whose_session_it_was(self):
        self.sign_in()
        jti = RefreshToken(self.refresh)["jti"]

        self.revoke(self.refresh)

        (event,) = self.audit_events("SESSION_REVOKE")
        self.assertEqual(event["metadata"], {"revoked_jti": jti, "user_id": self.user.pk})

    def test_an_unknown_session_is_a_404(self):
        response = self.client.delete("/api/v1/users/sessions/no-such-jti/", **self.admin_headers)

        self.assertEqual(response.status_code, 404)
        self.assertEqual(self.audit_events("SESSION_REVOKE"), [])
