"""
IR-663: responses carry the browser security headers (ASVS 14.4.3/4/6/7).

Two servers answer a browser, so two halves:

- **Django** sets them on everything it serves -- the API, the admin, and the
  static files WhiteNoise serves through it. `SecurityMiddleware` already sends
  `nosniff` and a Referrer-Policy and `XFrameOptionsMiddleware` already sends
  `DENY`; these tests pin them so a settings change cannot drop them silently.
  Django 5.2 has no CSP support, so `core.middleware.ContentSecurityPolicyMiddleware`
  adds that header.
- **nginx** serves the single-page app itself. It never sees Django's headers
  for those responses, so it adds its own, from `frontend/security-headers.conf`.
  A Django test client cannot reach nginx, so that half is read as text, like the
  IR-628 and IR-662 pins; the Docker Compose CI job also boots the real nginx
  and asks it.

The CSP ships as `Content-Security-Policy-Report-Only` until a manual
walk-through of the main screens shows no violation (IR-663's acceptance
criteria). Report-only is not enforcement, and browsers ignore
`frame-ancestors` in a report-only policy, which is why `X-Frame-Options: DENY`
stays on both servers.
"""

import re

import pytest
from django.test import SimpleTestCase, override_settings

from apps.documents.tests.test_document_access_control import NEEDS_CHECKOUT, REPO_ROOT

SNIPPET_INCLUDE_PATH = "/etc/nginx/iris/security-headers.conf"

# A referrer policy that sends no more than strict-origin-when-cross-origin.
ACCEPTABLE_REFERRER_POLICIES = {
    "no-referrer",
    "same-origin",
    "strict-origin",
    "strict-origin-when-cross-origin",
}


def parse_csp(policy):
    """`{directive: [sources]}` for a CSP header value."""
    directives = {}
    for part in policy.split(";"):
        tokens = part.split()
        if tokens:
            directives.setdefault(tokens[0].lower(), tokens[1:])
    return directives


def assert_policy_is_strict(policy):
    """The properties IR-663 asks of every CSP this repository ships."""
    directives = parse_csp(policy)
    scripts = directives.get("script-src", directives.get("default-src"))
    assert scripts is not None, "the policy restricts no script source"
    assert "'unsafe-inline'" not in scripts, "inline script is allowed"
    assert "'unsafe-eval'" not in scripts, "eval is allowed"
    assert "*" not in scripts, "script from any origin is allowed"
    assert directives.get("frame-ancestors") == ["'none'"]
    assert directives.get("object-src") == ["'none'"]
    assert "base-uri" in directives, "a <base> tag could re-point relative script URLs"
    for sources in directives.values():
        assert "*" not in sources and "http:" not in sources and "https:" not in sources, (
            f"a wildcard source in {policy!r}"
        )


# ---- Django ----------------------------------------------------------------


class DjangoResponseHeaderTests(SimpleTestCase):
    """A 404 goes through the whole middleware stack and touches no database."""

    def get(self, path="/api/v1/no-such-endpoint/"):
        return self.client.get(path)

    def test_nosniff(self):
        self.assertEqual(self.get()["X-Content-Type-Options"], "nosniff")

    def test_referrer_policy_is_strict_origin_when_cross_origin_or_stricter(self):
        self.assertIn(self.get()["Referrer-Policy"], ACCEPTABLE_REFERRER_POLICIES)

    def test_framing_is_denied(self):
        self.assertEqual(self.get()["X-Frame-Options"], "DENY")

    def test_csp_ships_report_only(self):
        response = self.get()
        self.assertIn("Content-Security-Policy-Report-Only", response)
        self.assertNotIn(
            "Content-Security-Policy",
            response,
            "the CSP is enforced before the IR-663 walk-through found it clean",
        )

    def test_csp_is_strict(self):
        assert_policy_is_strict(self.get()["Content-Security-Policy-Report-Only"])

    def test_admin_pages_carry_it_too(self):
        self.assertIn("Content-Security-Policy-Report-Only", self.get("/admin/login/"))

    @override_settings(CONTENT_SECURITY_POLICY_REPORT_ONLY=False)
    def test_enforcing_is_one_setting(self):
        response = self.get()
        self.assertIn("Content-Security-Policy", response)
        self.assertNotIn("Content-Security-Policy-Report-Only", response)

    @override_settings(CONTENT_SECURITY_POLICY="")
    def test_no_policy_sends_no_header(self):
        response = self.get()
        self.assertNotIn("Content-Security-Policy", response)
        self.assertNotIn("Content-Security-Policy-Report-Only", response)


# ---- nginx -----------------------------------------------------------------


def _frontend(name):
    """A file under frontend/, or a skip where the checkout is not mounted."""
    if REPO_ROOT is None:
        pytest.skip(NEEDS_CHECKOUT)
    return (REPO_ROOT / "frontend" / name).read_text(encoding="utf-8")


def _snippet_headers():
    """`{name: value}` for every `add_header` in the snippet, which must be `always`."""
    text = _without_comments(_frontend("security-headers.conf"))
    found = re.findall(
        r'^\s*add_header\s+(\S+)\s+"([^"]*)"\s*(always)?\s*;', text, re.MULTILINE
    )
    assert len(found) == len(re.findall(r"\badd_header\b", text)), (
        "an add_header line this test cannot read; quote its value"
    )
    headers = {}
    for name, value, always in found:
        assert always, f"{name} is missing `always`, so error responses would lack it"
        headers[name] = value
    return headers


def _location_blocks(conf):
    """`[(location line, body)]` for each location block, nested ones included."""
    blocks = []
    for match in re.finditer(r"^\s*location\b[^{]*\{", conf, re.MULTILINE):
        depth, i = 1, match.end()
        while depth:
            depth += {"{": 1, "}": -1}.get(conf[i], 0)
            i += 1
        blocks.append((match.group(0).strip(), conf[match.end():i - 1]))
    return blocks


def _without_comments(text):
    return re.sub(r"#[^\n]*", "", text)


def test_the_snippet_sends_every_header():
    headers = _snippet_headers()
    assert headers.get("X-Content-Type-Options") == "nosniff"
    assert headers.get("Referrer-Policy") in ACCEPTABLE_REFERRER_POLICIES
    assert headers.get("X-Frame-Options") == "DENY"
    assert "Content-Security-Policy-Report-Only" in headers, (
        "the SPA's CSP must ship report-only until the IR-663 walk-through is clean"
    )
    assert "Content-Security-Policy" not in headers
    assert_policy_is_strict(headers["Content-Security-Policy-Report-Only"])


def test_every_location_nginx_answers_itself_includes_the_snippet():
    """
    nginx inherits `add_header` into a location only when that location sets
    none of its own -- the asset location sets Cache-Control -- so a server-level
    header would silently vanish from every JS and CSS file. Each location that
    serves files includes the snippet instead. Proxied locations do not: Django
    sets the same headers, and nginx would send them twice.
    """
    conf = _without_comments(_frontend("nginx.conf"))
    blocks = _location_blocks(conf)
    assert blocks, "no location blocks found -- has nginx.conf changed shape?"
    served = [(line, body) for line, body in blocks if "proxy_pass" not in body]
    assert served, "nginx serves nothing itself?"
    for line, body in served:
        assert re.search(rf"include\s+{re.escape(SNIPPET_INCLUDE_PATH)}\s*;", body), (
            f"`{line}` serves the SPA without the security headers"
        )
    for line, body in blocks:
        if "proxy_pass" in body:
            assert "security-headers.conf" not in body, f"`{line}` would duplicate Django's"


def test_the_image_puts_the_snippet_where_nginx_includes_it():
    dockerfile = _frontend("Dockerfile")
    assert re.search(
        rf"^COPY\s+security-headers\.conf\s+{re.escape(SNIPPET_INCLUDE_PATH)}\s*$",
        dockerfile,
        re.MULTILINE,
    ), "the frontend image does not ship the snippet nginx.conf includes"
