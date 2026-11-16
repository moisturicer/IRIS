"""
nginx looks the backend up per request, not once at startup (IR-200).

A literal `proxy_pass http://backend:8000` makes nginx resolve `backend` when
it loads and keep that address, so recreating the backend container broke
every API call until nginx restarted. A variable upstream plus Docker's
resolver makes nginx ask again. These pins read the configs as text, like the
other nginx tests: the backend container has no nginx. The behaviour itself is
proved against a real nginx by scripts/check_nginx_backend_resolution.sh in CI.
"""

import re
from pathlib import Path

import pytest

from testing.nginx import location_blocks

FRONTEND = Path(__file__).resolve().parents[3] / "frontend"
CONFIGS = ("nginx.conf", "nginx.dev.conf", "runtime-edge.conf")
RESOLVER = re.compile(r"^\s*resolver\s+127\.0\.0\.11\b[^;]*\bvalid=\d+s\b[^;]*;", re.MULTILINE)


def _read(name):
    path = FRONTEND / name
    if not path.exists():
        pytest.skip(f"frontend/{name} is not mounted in the backend container")
    lines = path.read_text(encoding="utf-8").splitlines()
    return "\n".join(line.split("#", 1)[0] for line in lines)


@pytest.mark.parametrize("name", CONFIGS)
def test_no_location_proxies_to_a_literal_backend_address(name):
    conf = _read(name)
    literal = re.findall(r"proxy_pass\s+http://backend[:/;][^;]*;", conf)
    assert not literal, f"{name} pins the backend's startup address again: {literal}"


@pytest.mark.parametrize("name", ("nginx.conf", "nginx.dev.conf"))
def test_the_server_has_dockers_resolver(name):
    assert RESOLVER.search(_read(name)), f"{name} has no resolver, so a variable upstream can't be looked up"


@pytest.mark.parametrize("name", CONFIGS)
def test_every_backend_location_sets_the_variable_it_proxies_to(name):
    for line, body in location_blocks(_read(name)):
        if "$iris_backend" not in body:
            continue
        assert re.search(r"\bset\s+\$iris_backend\s+backend:8000\s*;", body), (
            f"`{line}` in {name} proxies to $iris_backend without setting it"
        )
