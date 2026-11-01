"""`python -m ai.runs.purge`: remove deleted accounts' Conversations (IR-722)."""

import asyncio

from ai.infrastructure.settings import settings
from ai.runs.store import RunStore


def main() -> None:
    if not settings.RUNS_DATABASE_URL:
        raise SystemExit("RUNS_DATABASE_URL is required")
    purged = asyncio.run(RunStore(settings.RUNS_DATABASE_URL).purge_departed())
    print(f"purged {purged} conversation(s)")


if __name__ == "__main__":
    main()
