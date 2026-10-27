"""An independent process that admits provider attempts (IR-545).

Run by `test_shared_processes.py` as ``python -m apps.ai.admission.tests.probe
MODE COUNT START_AT``, with its limits in the environment, against the test
database. It shares nothing with the test process but Postgres, which is the
point: any agreement between them is the shared store's doing.

MODE ``spend`` admits and settles; ``hold`` admits and keeps every attempt
open; ``crash`` admits once and dies without settling. Prints one JSON line:
how many were admitted and why the rest were refused.
"""

import json
import os
import sys
import time


def main() -> None:
    import django

    django.setup()

    from apps.ai.admission import errors, ledger, scope

    mode, count, start_at = sys.argv[1], int(sys.argv[2]), float(sys.argv[3])
    request = ledger.Request(
        operation="llm", default_lane="research", account="probe-account", models=("cheap",),
        input_tokens=10, output_tokens=10,
        timeout_seconds=float(os.environ.get("PROBE_TIMEOUT", "10")),
    )
    time.sleep(max(0.0, start_at - time.time()))  # start together
    admitted, refused = 0, []
    ceiling = None
    if os.environ.get("PROBE_COMPARISON"):
        from apps.ai.comparison_configuration import comparison_ceiling
        ceiling = comparison_ceiling()
    with scope.run(scope.new_run(os.environ.get("PROBE_RUN_KEY"), ceiling=ceiling)):
        for _ in range(count):
            try:
                ticket = ledger.admit(request)
            except errors.AdmissionDenied as denied:
                refused.append(denied.reason)
                continue
            admitted += 1
            if mode == "spend":
                ticket.settle(scope.AttemptUsage(sent=True, input_tokens=10, output_tokens=10))
            if mode == "crash":
                print(json.dumps({"admitted": admitted, "refused": refused}), flush=True)
                os._exit(1)
    print(json.dumps({"admitted": admitted, "refused": refused}), flush=True)


if __name__ == "__main__":
    main()
