"""Every long-running IRIS service comes back by itself after the server starts (IR-1015).

A scheduled stop and start (deploy/aws/iris-guards.yaml) or a recovery reboots
the server with nobody logged in, so only Docker brings IRIS back. That holds
while each service in docker-compose.prod.yml says `restart: unless-stopped` or
`always`. One-shot jobs exit when done and are listed here by name.

    python deploy/tests/check_restart_policies.py [compose file]
"""

import sys
from pathlib import Path

import yaml

ONE_SHOT = {"migrate"}  # runs the migrations, then exits
COMES_BACK = {"unless-stopped", "always"}


def problems(compose: dict) -> list[str]:
    services = compose.get("services") or {}
    found = []
    for name, service in services.items():
        restart = (service or {}).get("restart")
        if name in ONE_SHOT:
            continue
        if restart not in COMES_BACK:
            found.append(f"{name}: restart is {restart!r}, so it stays down after the server starts")
    for name in sorted(ONE_SHOT - services.keys()):
        found.append(f"{name}: listed as one-shot here but not in the compose file; update ONE_SHOT")
    return found


def main() -> int:
    path = Path(sys.argv[1] if len(sys.argv) > 1 else "docker-compose.prod.yml")
    found = problems(yaml.safe_load(path.read_text(encoding="utf-8")))
    for line in found:
        print(f"FAIL {line}")
    if found:
        return 1
    print(f"ok   every long-running service in {path} restarts by itself")
    return 0


if __name__ == "__main__":
    sys.exit(main())
