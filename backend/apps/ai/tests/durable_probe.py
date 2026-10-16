"""Independent durable worker probe; only Postgres and stdin cross processes.

Legacy probes replace answer orchestration; controller probes replace providers only.
Claims, admission, guarded Turn
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

    if mode in ("controller_crash", "controller_deliver"):
        from apps.ai.composition import CompositionRoot
        from apps.ai.controller.versions import CONTROLLER_ENGINE
        from apps.ai.inference import InferenceTask
        from apps.ai.models import VECTOR_COLUMN_DIMENSIONS
        from apps.ai.providers.fakes import DeterministicEmbeddingProvider, ScriptedToolCallingLLM

        class Planner(MeteredAdapter):
            calls = 0

            def converse_with_tools(self, messages, tools, *, timeout_seconds=None):
                super().converse_with_tools(messages, tools, timeout_seconds=timeout_seconds)
                self.calls += 1
                if mode == "controller_crash" and self.calls == 2:
                    # The real controller charged round/prompt; admission committed
                    # the physical reservation; this remote usage is now unknown.
                    emit(controller_crashed=True)
                    os._exit(23)
                return ScriptedToolCallingLLM.calling(
                    "aggregate_records", '{"operation":"count"}', "count-1",
                )

        planner = AdmittedLLMProvider(Planner())
        writer = AdmittedLLMProvider(MeteredAdapter(text="A supported answer."))
        root = CompositionRoot(
            embedder=DeterministicEmbeddingProvider(dimensions=VECTOR_COLUMN_DIMENSIONS),
            llm=writer, permits=lambda record: True, engine=CONTROLLER_ENGINE,
        )
        real = root.llm_for
        root.llm_for = lambda task, **kwargs: planner if task == InferenceTask.PLAN else real(task, **kwargs)
        with use_composition_root(root):
            durable.execute(run_id)
        emit(delivered=True, planner_calls=planner._adapter.calls)
        return

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
