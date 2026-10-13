"""Write only identifiers, digests, codes and measurements to the run audit."""

import hashlib
import json
import time
import uuid
from dataclasses import dataclass
from typing import Optional

from apps.ai.models.research import ResearchRun, ResearchStep


def argument_digest(arguments: object) -> str:
    try:
        canonical = json.dumps(json.loads(arguments), sort_keys=True, separators=(",", ":"))
    except (TypeError, ValueError):
        canonical = str(arguments)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class Step:
    kind: str
    status: str
    tool: str = ""
    argument_digest: str = ""
    duplicate: bool = False
    latency_ms: int = 0
    input_tokens: Optional[int] = None
    output_tokens: Optional[int] = None


class RunAudit:
    def __init__(self, ctx, clock=time.monotonic):
        self.clock = clock
        self.started = clock()
        self.steps: list[Step] = []
        self.row = ResearchRun.objects.create(
            id=uuid.UUID(ctx.run_id), user=ctx.user, conversation_id=ctx.conversation_id,
        )

    def append(self, step: Step) -> None:
        from dataclasses import asdict

        ResearchStep.objects.create(run=self.row, position=len(self.steps), **asdict(step))
        self.steps.append(step)

    def finish(self, *, status, reason, prompt_tokens, validation_codes=()) -> None:
        self.row.status = status
        self.row.stop_reason = reason
        self.row.prompt_tokens = max(0, prompt_tokens)
        self.row.output_tokens = sum(s.output_tokens or 0 for s in self.steps)
        self.row.latency_ms = max(0, int((self.clock() - self.started) * 1000))
        self.row.validation_codes = list(validation_codes)
        self.row.save(update_fields=[
            "status", "stop_reason", "prompt_tokens", "output_tokens", "latency_ms", "validation_codes",
        ])
