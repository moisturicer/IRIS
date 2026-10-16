"""Independent durable worker probe; only Postgres and stdin cross processes.

The scripted answer replaces generation only. Claims, admission, guarded Turn
writes, conversation-state commits and the public journal use production code.
A ready JSON line followed by a stdin gate fixes race ordering without sleeps.
"""

import json
import os
import sys


def emit(**data):
    print(json.dumps(data), flush=True)


def main():
    import django

    django.setup()

    from apps.ai import durable
    from apps.ai.admission import errors, scope
    from apps.ai.admission.llm import AdmittedLLMProvider
    from apps.ai.admission.tests.support import MeteredAdapter
    from apps.ai.answers.citations import GroundedAnswer
    from apps.ai.composition import use_composition_root
    from apps.ai.models import AskRun
    from apps.ai.orchestrator import ChatQuestion
    from apps.ai.tests.corpus import root_with

    mode, run_id = sys.argv[1:3]

    def record(attempt):
        run = AskRun.objects.select_related("conversation").get(pk=attempt.run_id)
        asked = ChatQuestion(
            conversation=run.conversation, question="probe question",
            effective_question="probe question", resolved_question=None,
            history=[], widened=False, scope_record=None,
            context_revision=run.request.get("context_revision", 0),
        )
        with use_composition_root(root_with()):
            orchestrator = durable._QueuedOrchestrator(asked, max_sources=1, attempt=attempt)
            return orchestrator._record(GroundedAnswer(text="scripted answer", citations=()))

    if mode == "deliver":
        # The real delivery/claim boundary, with deterministic generation.
        durable._answer = record
        durable.execute(run_id)
        emit(delivered=True)
        return

    attempt = durable.claim(run_id)
    assert attempt is not None, "probe requires an unfinished run"
    if mode == "crash":
        durable.append(attempt, "text_delta", {"text": "unfinished"})
        emit(claimed=str(attempt.pk))
        os._exit(23)

    run = AskRun.objects.get(pk=run_id)
    run_scope = durable.run_scope(run, attempt=attempt)
    adapter = MeteredAdapter(stream_usage=(120, 30))
    provider = AdmittedLLMProvider(adapter)
    with scope.run(run_scope):
        # Keep one already-sent call open across cancellation/supersession.
        stream = provider.stream("system", "question")
        next(stream)
        emit(ready=str(attempt.pk), sent=adapter.sent)
        assert sys.stdin.readline().strip() == "continue"
        stream.close()
        try:
            provider.generate("system", "another question")
        except errors.AdmissionDenied as denied:
            refusal = denied.reason
        else:
            refusal = None

    writes = {}
    operations = {
        "append": lambda: durable.append(attempt, "text_delta", {"text": "stale"}),
        "finish": lambda: durable.finish_without_turn(attempt, "failed", "stale"),
        "turn": lambda: record(attempt),
    }
    for name, operation in operations.items():
        try:
            operation()
        except durable.StaleAttempt:
            writes[name] = "fenced"
        else:
            writes[name] = "written"
    emit(refusal=refusal, sent=adapter.sent, writes=writes)


if __name__ == "__main__":
    main()
