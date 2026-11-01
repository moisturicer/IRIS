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
from pathlib import Path

import pytest
from django.test import SimpleTestCase, override_settings

REPO_ROOT = Path(__file__).resolve().parents[3]
NGINX_CONF = REPO_ROOT / "frontend" / "nginx.conf"
NGINX_SNIPPET = REPO_ROOT / "frontend" / "security-headers.conf"
FRONTEND_DOCKERFILE = REPO_ROOT / "frontend" / "Dockerfile"
SNIPPET_INCLUDE_PATH = "/etc/nginx/iris/security-headers.conf"

# A referrer policy that sends no more than strict-origin-when-cross-origin.
ACCEPTABLE_REFERRER_POLICIES = {
    "no-referrer",
    "same-origin",
    "strict-origin",
    "strict-origin-when-cross-origin",
}
CSP_HEADERS = ("Content-Security-Policy", "Content-Security-Policy-Report-Only")


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

    def headers(self, path="/api/v1/no-such-endpoint/"):
        return self.client.get(path)

    def test_nosniff(self):
        self.assertEqual(self.headers()["X-Content-Type-Options"], "nosniff")

    def test_referrer_policy_is_strict_origin_when_cross_origin_or_stricter(self):
        self.assertIn(self.headers()["Referrer-Policy"], ACCEPTABLE_REFERRER_POLICIES)

    def test_framing_is_denied(self):
        self.assertEqual(self.headers()["X-Frame-Options"], "DENY")

    def test_csp_ships_report_only(self):
        response = self.headers()
        self.assertIn("Content-Security-Policy-Report-Only", response)
        self.assertNotIn(
            "Content-Security-Policy",
            response,
            "the CSP is enforced before the IR-663 walk-through found it clean",
        )

    def test_csp_is_strict(self):
        assert_policy_is_strict(self.headers()["Content-Security-Policy-Report-Only"])

    def test_admin_pages_carry_it_too(self):
        self.assertIn("Content-Security-Policy-Report-Only", self.headers("/admin/login/"))

    @override_settings(CONTENT_SECURITY_POLICY_REPORT_ONLY=False)
    def test_enforcing_is_one_setting(self):
        response = self.headers()
        self.assertIn("Content-Security-Policy", response)
        self.assertNotIn("Content-Security-Policy-Report-Only", response)

    @override_settings(CONTENT_SECURITY_POLICY="")
    def test_no_policy_sends_no_header(self):
        response = self.headers()
        for name in CSP_HEADERS:
            self.assertNotIn(name, response)


# ---- nginx -----------------------------------------------------------------


def _needs_frontend():
    if not NGINX_CONF.exists():
        pytest.skip("frontend/ is not mounted in the backend container")


def _snippet_headers():
    """`{name: value}` for every `add_header` in the snippet, which must be `always`."""
    text = NGINX_SNIPPET.read_text(encoding="utf-8")
    headers = {}
    for name, value, always in re.findall(
        r'^\s*add_header\s+(\S+)\s+"([^"]*)"\s*(always)?\s*;', text, re.MULTILINE
    ):
        assert always, f"{name} is missing `always`, so error responses would lack it"
        headers[name] = value
    return headers


def _location_blocks(conf):
    """`[(location line, body)]` for each top-level location in the server block."""
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
    _needs_frontend()
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
    _needs_frontend()
    conf = _without_comments(NGINX_CONF.read_text(encoding="utf-8"))
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
    _needs_frontend()
    dockerfile = FRONTEND_DOCKERFILE.read_text(encoding="utf-8")
    assert re.search(
        rf"^COPY\s+security-headers\.conf\s+{re.escape(SNIPPET_INCLUDE_PATH)}\s*$",
        dockerfile,
        re.MULTILINE,
    ), "the frontend image does not ship the snippet nginx.conf includes"
