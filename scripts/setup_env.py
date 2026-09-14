"""Create the environment files this repository needs, without clobbering.

Run from anywhere:  python scripts/setup_env.py

IR-154 made the database credential a required, un-defaulted value and gave
Docker Compose its own repo-root `.env` to interpolate from. That is the right
shape, but it breaks two things for anyone with an existing checkout, and both
failures are worth automating away rather than documenting and hoping:

1. `docker compose up` now stops with "required variable DB_NAME is missing"
   until a repo-root `.env` exists. That file is new, so nobody has one.
2. Worse, writing *fresh* credentials into it breaks an existing
   `postgres_data` volume. `POSTGRES_*` is read only on first init, so the
   volume keeps the credentials it was built with and the new ones simply fail
   authentication -- with a "password authentication failed" that says nothing
   about why.

So the root `.env` is derived from `backend/.env` when one exists: the values
then match the volume that is already on disk, and (2) cannot happen. Only a
genuinely fresh checkout gets generated values.

Never overwrites a file that exists. Safe to run repeatedly.
"""

from __future__ import annotations

import secrets
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
ROOT_ENV = REPO_ROOT / ".env"
BACKEND_ENV = REPO_ROOT / "backend" / ".env"
BACKEND_EXAMPLE = REPO_ROOT / "backend" / ".env.example"

# The three Compose interpolates. Django reads them from backend/.env; the db
# service needs them as POSTGRES_* at container-creation time.
DB_KEYS = ("DB_NAME", "DB_USER", "DB_PASSWORD")

# Values that were committed to the repository before IR-154 and are burned.
# Generating one of these would defeat the point of the ticket.
RETIRED = {"iris_db", "iris_user", "iris_password", "change-me-in-production"}


def read_env(path: Path) -> dict[str, str]:
    """Parse KEY=value lines. Not a full dotenv parser — enough for this."""
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def blank(value: str | None) -> bool:
    return value is None or not value.strip()


def write_root_env(values: dict[str, str], derived_from_backend: bool) -> None:
    origin = (
        "Derived from backend/.env so these match any postgres_data volume you\n"
        "# already have -- POSTGRES_* is only read on a volume's first init."
        if derived_from_backend
        else "Generated for a fresh checkout. Put the same three values in\n"
        "# backend/.env, or run this script again after creating it."
    )
    ROOT_ENV.write_text(
        "# Repo-root environment for Docker Compose (IR-154).\n"
        f"# {origin}\n"
        "# Written by scripts/setup_env.py. Gitignored; never commit it.\n\n"
        + "".join(f"{key}={values[key]}\n" for key in DB_KEYS),
        encoding="utf-8",
    )


def main() -> int:
    did_something = False

    # --- backend/.env -----------------------------------------------------
    backend = read_env(BACKEND_ENV)
    if not BACKEND_ENV.exists():
        if not BACKEND_EXAMPLE.exists():
            print(f"error: {BACKEND_EXAMPLE} is missing; is this the IRIS repo?")
            return 1
        text = BACKEND_EXAMPLE.read_text(encoding="utf-8")
        generated = {
            "SECRET_KEY": secrets.token_urlsafe(64),
            "DB_NAME": "iris_local",
            "DB_USER": "iris_local",
            "DB_PASSWORD": secrets.token_urlsafe(24),
        }
        for key, value in generated.items():
            text = text.replace(f"\n{key}=\n", f"\n{key}={value}\n")
        BACKEND_ENV.write_text(text, encoding="utf-8")
        backend = generated
        did_something = True
        print(f"created  {BACKEND_ENV.relative_to(REPO_ROOT)}  (generated SECRET_KEY and DB credentials)")
        print("         Create that Postgres role and database before migrating:")
        print(f"           CREATE USER {generated['DB_USER']} WITH PASSWORD '<the DB_PASSWORD in the file>';")
        print(f"           CREATE DATABASE {generated['DB_NAME']} OWNER {generated['DB_USER']};")
        print(f"           ALTER USER {generated['DB_USER']} CREATEDB;   -- needed to run the test suite")
    else:
        missing = [k for k in ("SECRET_KEY", *DB_KEYS) if blank(backend.get(k))]
        if missing:
            print(f"warning: {BACKEND_ENV.relative_to(REPO_ROOT)} has blank {', '.join(missing)}.")
            print("         These have no defaults since IR-154 - Django will refuse to start.")

    # --- repo-root .env ---------------------------------------------------
    if ROOT_ENV.exists():
        print(f"kept     {ROOT_ENV.relative_to(REPO_ROOT)}  (already exists, not touched)")
    else:
        from_backend = all(not blank(backend.get(k)) for k in DB_KEYS)
        if from_backend:
            values = {k: backend[k] for k in DB_KEYS}
        else:
            values = {
                "DB_NAME": "iris_local",
                "DB_USER": "iris_local",
                "DB_PASSWORD": secrets.token_urlsafe(24),
            }
            print("note:    backend/.env had no usable DB credentials, so these are generated.")
            print("         Put the SAME three values in backend/.env or the two will disagree.")
        write_root_env(values, derived_from_backend=from_backend)
        did_something = True
        source = "copied from backend/.env" if from_backend else "generated"
        print(f"created  {ROOT_ENV.relative_to(REPO_ROOT)}  ({source})")

    # --- warn about anything burned ---------------------------------------
    root = read_env(ROOT_ENV)
    burned = sorted({v for v in root.values() if v in RETIRED})
    if burned:
        print()
        print("WARNING: your configuration still uses credentials that were committed")
        print("         to this repository and are therefore public. They work, but")
        print("         rotate them before anything is exposed publicly (IR-157):")
        print("         drop the volume (`docker compose down -v`, destroys local data),")
        print("         set new values in BOTH .env files, and bring the stack back up.")

    if not did_something:
        print("\nNothing to do - both files were already in place.")
    else:
        print("\nDone. `docker compose up --build` should now get past interpolation.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
