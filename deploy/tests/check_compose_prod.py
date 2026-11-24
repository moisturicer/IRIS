"""What docker-compose.prod.yml must hold for a server nobody is logged in to.

1. Every long-running service comes back by itself after the server starts
   (IR-1015). A scheduled stop and start (deploy/aws/iris-guards.yaml) or a
   recovery reboots the server with nobody there, so only Docker brings IRIS
   back. That holds while each service says `restart: unless-stopped` or
   `always`. One-shot jobs exit when done and are listed here by name.
2. Every service's logs are rotated, so none can fill the disk (IR-1017):
   `json-file` with `max-size` and `max-file` set.
3. The AI schema is updated before the AI starts (IR-1320): `ai-gateway`
   and `ai-runs-worker` wait for `ai-migrate` to finish, and only
   `ai-migrate` holds the maintenance login (ADR-014, IR-826).

    python deploy/tests/check_compose_prod.py [compose file]
"""

import sys
from pathlib import Path

import yaml

ONE_SHOT = {"migrate", "ai-migrate"}  # each runs migrations, then exits
AI_SERVICES = ("ai-gateway", "ai-runs-worker")
MAINTENANCE_LOGIN = "RUNS_MIGRATION_DATABASE_URL"
COMES_BACK = {"unless-stopped", "always"}


def restart_problems(services: dict) -> list[str]:
    found = []
    for name, service in services.items():
        if name in ONE_SHOT:
            continue
        restart = (service or {}).get("restart")
        if restart not in COMES_BACK:
            found.append(f"{name}: restart is {restart!r}, so it stays down after the server starts")
    for name in sorted(ONE_SHOT - services.keys()):
        found.append(f"{name}: listed as one-shot here but not in the compose file; update ONE_SHOT")
    return found


def rotation_problems(services: dict) -> list[str]:
    found = []
    for name, service in services.items():
        logging = (service or {}).get("logging") or {}
        options = logging.get("options") or {}
        if logging.get("driver") != "json-file" or not options.get("max-size") or not options.get("max-file"):
            found.append(f"{name}: logs aren't rotated (json-file with max-size and max-file), so they can fill the disk")
    return found


def _environment(service: dict) -> list[str]:
    env = (service or {}).get("environment") or []
    return [f"{k}={v}" for k, v in env.items()] if isinstance(env, dict) else list(env)


def ai_schema_problems(services: dict) -> list[str]:
    found = []
    for name in AI_SERVICES:
        if name not in services:
            continue
        after = ((services[name] or {}).get("depends_on") or {}).get("ai-migrate") or {}
        if after.get("condition") != "service_completed_successfully":
            found.append(f"{name}: doesn't wait for ai-migrate to finish, so it can start against an older iris_ai")
    for name, service in services.items():
        if name == "ai-migrate":
            continue
        if any(line.split("=", 1)[0] == MAINTENANCE_LOGIN for line in _environment(service)):
            found.append(f"{name}: holds {MAINTENANCE_LOGIN}, which only ai-migrate may (ADR-014)")
    return found


def problems(compose: dict) -> list[str]:
    services = compose.get("services") or {}
    return restart_problems(services) + rotation_problems(services) + ai_schema_problems(services)


def main() -> int:
    path = Path(sys.argv[1] if len(sys.argv) > 1 else "docker-compose.prod.yml")
    found = problems(yaml.safe_load(path.read_text(encoding="utf-8")))
    for line in found:
        print(f"FAIL {line}")
    if found:
        return 1
    print(f"ok   every long-running service in {path} restarts by itself, every service's logs are rotated,"
          " and the AI waits for its schema")
    return 0


if __name__ == "__main__":
    sys.exit(main())
