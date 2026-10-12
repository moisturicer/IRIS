# Research lane rollout (IR-504)

How the research lane ([ADR-038](../adr/038-bounded-research-lane-for-ask-iris.md)) is served, reported and switched on. ADR-038 is still **Proposed**: this document describes what the code does, not an approval to enable it.

## Serving a 10–90 s run (proposal 13 D8)

**Decision: ASGI** ([ADR-017](../adr/017-asgi-deployment-for-gateway-streaming.md)). Production already runs `gunicorn config.asgi:application --worker-class uvicorn.workers.UvicornWorker` (`backend/Dockerfile`, `docker-compose.prod.yml`). Under ASGI Django runs each synchronous request on its own thread, so a long research run holds a thread and a connection, not one of the four workers.

What was missing was the stream itself. Django serves a synchronous `StreamingHttpResponse` under ASGI by reading the whole generator into a list first, so every SSE event — passage-lane text deltas included — reached the reader only after the answer had finished. `apps/ai/streaming.EventStreamResponse` fixes that: under ASGI it runs the generator in one call on the request's own thread and hands each chunk to the event loop as it is produced. One call keeps the generator's database connection and the run's deadline context variable in one place, as WSGI does. When the reader leaves, the generator is closed on that same thread after its current step, so an interrupted run still records how far it got (`ResearchRun.status = "interrupted"`).

| Option | Gains | Costs |
|---|---|---|
| **ASGI (chosen)** | Already deployed; progress flows through the existing `/ask/stream/` endpoint; no new queue, pub/sub relay or result store | A run holds a thread and an open connection for up to 90 s; a worker restart ends in-flight runs with no resume; gunicorn's `--timeout 120` must stay above `AI_RESEARCH_WALL_CLOCK_SECONDS` |
| Celery worker offload | Survives a closed browser and a web restart; runs are capped by worker concurrency | Needs a Redis pub/sub relay from worker to endpoint, a way to reattach a reader to a run, and the endpoint still holds a connection to stream; more moving parts for no reader-visible gain today |

The development server (`runserver`) is WSGI; there the response streams as before.

## Progress events

On the research lane the stream is `routing_decided`, `retrieval_started`, then one `agent_step` per planner step, then `done`.

```
event: agent_step
data: {"position": 3, "kind": "tool", "status": "running", "tool": "search_passages", ...}

event: agent_step
data: {"position": 3, "kind": "tool", "status": "ok", "tool": "search_passages",
       "duplicate": false, "latency_ms": 412, "coverage": "sample", "found": 6}
```

A step is sent `running` before it starts and again at the same `position` with its outcome. `kind` is `plan` (a planner model call), `tool` or `answer`. A step carries names, codes and counts only — never the question, the planner's arguments or notes, or corpus text. `done.research` (and the `/ask/` JSON body) carries the finished steps and `coverage_notes`, which the Turn stores in `Turn.research` (migration `0022`) and a reopened transcript replays. Coverage notes — the run stopped at a limit, or weaker passages were dropped — moved out of the answer text into `coverage_notes`, so they no longer feed model history.

A client that does not know `agent_step` ignores it; the frontend's stream hook ignores any unknown event type.

## Turning it on

`AI_RESEARCH_LANE` takes `off` (default), `staff` or `on`. With `off`, no router or provider is constructed and both endpoints behave exactly as before. `staff` routes questions from office staff (KTTO, RDCO, ITSO, IERC — `core.permissions.is_office_staff`) and leaves every other user on the `off` path. `on` routes everyone. IR-515's refusal of `on` with `DEBUG=False` is lifted.

Rollout:

1. Confirm ADR-038 is accepted by a named person, and the Jev and vendor terms its §Consequences name.
2. Set `AI_RESEARCH_LANE=staff` and restart the backend containers. Staff use Ask IRIS; review their runs in `ResearchRun`/`ResearchStep` and the `research run finished` log lines.
3. When a person approves reader exposure, set `AI_RESEARCH_LANE=on` and restart.

Rollback: set `AI_RESEARCH_LANE=off` and restart. Turns already written keep their `routing` and `research` and replay unchanged; new questions take the passage pipeline. If routing itself misbehaves, `AI_JEV_ROUTING_ENABLED=false` is the second switch (ADR-038 §Consequences).

Production answers stay empty until IR-250: the disclosure gate refuses every record until `Record` has an embargo field.

## Logging

One `INFO` line per run from `apps.ai.research.planner`, `research run finished key=value ...` (also attached as record extras), with `run_id`, `status`, `stop_reason`, `limit_hit`, `fallback`, `malformed_calls`, `validation_codes`, `tool_calls`, `latency_ms`, `prompt_tokens` and `output_tokens`. The tool registry (`apps.ai.research.registry`, IR-509) also logs each limit hit and each rejected call; their reason codes are record extras only, which the standard formatter does not print. None of these carry question, argument or corpus text.
