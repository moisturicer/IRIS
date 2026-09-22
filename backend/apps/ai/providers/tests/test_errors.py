"""The classification vocabulary itself (IR-320).

Pure functions over a status code or a message -- no vendor account, no
Django, nothing to fake. The adapters' own suites assert that a *real* vendor
exception maps through these correctly; this asserts the mapping rules.
"""

from apps.ai.providers.errors import ErrorKind, classify_message, classify_status_code


class StatusCodeClassificationTests:
    def test_401_and_403_are_auth(self):
        assert classify_status_code(401, None, "") == ErrorKind.AUTH
        assert classify_status_code(403, None, "") == ErrorKind.AUTH

    def test_429_is_rate_limit(self):
        assert classify_status_code(429, None, "") == ErrorKind.RATE_LIMIT

    def test_a_400_naming_context_length_in_its_code_is_context_overflow(self):
        assert (
            classify_status_code(400, "context_length_exceeded", "")
            == ErrorKind.CONTEXT_OVERFLOW
        )

    def test_a_400_naming_context_length_in_its_message_is_context_overflow(self):
        assert (
            classify_status_code(400, None, "This model's maximum context length is 4096")
            == ErrorKind.CONTEXT_OVERFLOW
        )

    def test_a_400_with_no_context_hint_is_unknown(self):
        """Not every bad request is an oversized prompt -- a malformed field
        is a real error too, just not one this vocabulary names."""
        assert classify_status_code(400, None, "invalid parameter") == ErrorKind.UNKNOWN

    def test_5xx_is_network(self):
        """The vendor's own server error, not "our" network -- but the same
        shape of transient failure a caller would want to retry or degrade."""
        assert classify_status_code(500, None, "") == ErrorKind.NETWORK
        assert classify_status_code(503, None, "") == ErrorKind.NETWORK

    def test_an_unmapped_status_is_unknown(self):
        assert classify_status_code(404, None, "") == ErrorKind.UNKNOWN
        assert classify_status_code(409, None, "") == ErrorKind.UNKNOWN


class MessageClassificationTests:
    """The fallback path -- used only when there is no status code to read,
    e.g. a bare exception a test double raises with nothing but text."""

    def test_a_timeout_phrase_is_timeout(self):
        assert classify_message("Request timed out after 30s") == ErrorKind.TIMEOUT

    def test_a_rate_limit_phrase_is_rate_limit(self):
        assert classify_message("429 rate limited") == ErrorKind.RATE_LIMIT

    def test_an_auth_phrase_is_auth(self):
        assert classify_message("401 Unauthorized") == ErrorKind.AUTH
        assert classify_message("Forbidden: invalid API key") == ErrorKind.AUTH

    def test_a_connection_phrase_is_network(self):
        assert classify_message("Connection reset by peer") == ErrorKind.NETWORK

    def test_a_context_length_phrase_is_context_overflow(self):
        assert (
            classify_message("maximum context length is 4096 tokens")
            == ErrorKind.CONTEXT_OVERFLOW
        )

    def test_an_unrecognised_message_is_unknown(self):
        assert classify_message("the model returned no choices") == ErrorKind.UNKNOWN
