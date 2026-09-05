# AGENTS.md — IRIS

**The guidance for this repository lives in [`CLAUDE.md`](CLAUDE.md). Read that. This file is a pointer, not a second copy.**

This file exists because some tools look for `AGENTS.md` by convention. It deliberately holds no guidance of its own.

## Why it is a pointer

It used to be a full copy of `CLAUDE.md` — same headings, same architecture table, same rules. Two documents claiming to describe the same system is a documentation bug waiting to happen, and it happened: the copy drifted. By the time anyone noticed, this file was telling agents that the baseline branch was `refactor/docker-service` (retired, and fully contained in `main`) and that the AI gateway "does not exist" (it does, and [ADR-014](docs/adr/014-ai-gateway-as-a-service.md) has since adopted it).

An agent reading the stale copy would have branched from a dead ref and been told not to build the thing the ADRs now call for. That is worse than having no `AGENTS.md` at all, because it is wrong with authority.

`CLAUDE.md` is the single copy. If something belongs in agent guidance, it belongs there.

## The hierarchy this sits under

`CLAUDE.md` is itself downstream of the real authorities. In order:

1. [`docs/SRS.md`](docs/SRS.md) — requirements
2. [`docs/SDD.md`](docs/SDD.md) — system and design
3. [`docs/adr/`](docs/adr/) — architectural decisions and rationale
4. [`docs/engineering/`](docs/engineering/) — how the team builds, tests, reviews, releases
5. Code and tests — actual behaviour
6. Jira — planning and tracking, **never a requirements authority**

When these conflict, the higher one wins **and the lower one is corrected**. Do not silently reconcile — record the contradiction. That rule is why this file is now four paragraphs instead of a hundred lines.
