"""One reviewer's packet for a collected run (IR-607, IR-721). Reads the database, no vendor.

    python manage.py eval_review_packets --run run.json --reviewer EMAIL \\
        --reviewer-name "Name" --out packets.json

A packet holds no text: which turns the reviewer may see, the Records and source
revisions each rests on, citation markers and pages, and a blank review. Access
is `Record.objects.visible_to(reviewer)` now, so a revoked source is withheld
even if the evaluation reader once saw it.

To read the turns, render them from the run file the packet pins. Every turn is
judged again by that account's access and each source's current revision, and
the text is printed, never written to a file:

    python manage.py eval_review_packets --show packets.json --run run.json \\
        --reviewer EMAIL --reviewer-name "Name"

`--reopen packets.json --out reopened.json` writes the packet again for an
account (still without text), replacing another reviewer's review with a blank
one. The run file itself still holds every answer and stays with the operator.
"""

import json
from pathlib import Path

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from apps.ai.evaluation.conversations import postdates_lock
from apps.ai.evaluation.review_packets import (PacketRefused, build_packets, cited_ids,
                                               packet_ids, reauthorize, render)
from apps.ai.evaluation.runfile import file_digest, load_json, write_json
from apps.ai.grants.reads import research_records
from apps.ai.models import ChunkSet


class Command(BaseCommand):
    help = "Write, re-check or render a review packet holding only what one reviewer may read."

    def add_arguments(self, parser):
        parser.add_argument("--run", help="The collected run (to package, or to render from).")
        parser.add_argument("--reopen", help="A written packet to write again for the reviewer.")
        parser.add_argument("--show", help="A written packet to render for the reviewer now; "
                            "needs --run, prints and writes nothing.")
        parser.add_argument("--reviewer", required=True, help="The reviewer's login email.")
        parser.add_argument("--reviewer-name", help="The name the reviewer signs reviews with.")
        parser.add_argument("--out", help="Where to write the packet (--run, --reopen).")
        parser.add_argument("--lock", help="The set lock; required for held-out output.")

    def handle(self, *args, **options):
        mode = [m for m in ("reopen", "show") if options.get(m)]
        if len(mode) > 1 or (not mode and not options.get("run")):
            raise CommandError("give one of --run, --reopen or --show")
        if options.get("reopen") and options.get("run"):
            raise CommandError("give one of --run, --reopen or --show")
        user = get_user_model().objects.filter(email=options["reviewer"]).first()
        if user is None:
            raise CommandError(f"no user {options['reviewer']}")
        if not (options.get("reviewer_name") or "").strip():
            raise CommandError("a reviewer name is required")
        name = options["reviewer_name"].strip()
        if options.get("show"):
            if not options.get("run"):
                raise CommandError("--show needs --run: the text is rendered from the run file")
            return self._show(user, name, options)
        if not options.get("out"):
            raise CommandError("--out is required with --run or --reopen")
        if options.get("reopen"):
            if options.get("lock"):
                raise CommandError("--lock applies to --run only: a written packet was checked "
                                   "against the lock when it was built")
            written = load_json(options["reopen"])
            readable, revisions = _access(user, packet_ids(written))
            bundle = reauthorize(written, readable=readable, revisions=revisions, reviewer=name)
            return self._write(options["out"], bundle, "this account")
        run = load_json(options["run"])
        self._check_lock(run, options)
        readable, revisions = _access(user, cited_ids(run))
        bundle = build_packets(run, reviewer=name, readable=readable, revisions=revisions,
                               run_sha256=file_digest(options["run"]))
        self._write(options["out"], bundle, "this reviewer")

    @staticmethod
    def _check_lock(run, options):
        if any(row.get("split") == "held_out" for row in run.get("conversations", ())):
            lock = load_json(options["lock"]) if options["lock"] else {}
            if not postdates_lock((run.get("manifest") or {}).get("timestamp_utc"), lock):
                raise CommandError("held-out output opens only after the lock froze its "
                                   "prompts and rubric; pass --lock and a later run")

    def _show(self, user, name, options):
        written = load_json(options["show"])
        run = load_json(options["run"])
        self._check_lock(run, options)
        readable, revisions = _access(user, packet_ids(written) | cited_ids(run))
        bundle = reauthorize(written, readable=readable, revisions=revisions, reviewer=name)
        try:
            shown = render(bundle, run, file_digest(options["run"]), readable=readable,
                           revisions=revisions)
        except PacketRefused as exc:
            raise CommandError(str(exc)) from None
        self.stdout.write(json.dumps(shown, indent=2, ensure_ascii=False))

    def _write(self, out, bundle, whom):
        Path(out).parent.mkdir(parents=True, exist_ok=True)
        write_json(out, bundle)
        withheld = sum(t["withheld"] for p in bundle["packets"] for t in p["turns"])
        self.stdout.write(f"wrote {out}: {len(bundle['packets'])} conversations, "
                          f"{withheld} turns withheld from {whom}; no text is stored")


def _access(user, ids):
    """The Records `user` may read among `ids` now, and each one's active source revision."""
    readable = set(research_records(user).filter(pk__in=ids).values_list("pk", flat=True))
    revisions = dict(ChunkSet.objects.filter(record_id__in=readable, is_active=True)
                     .values_list("record_id", "id"))
    return readable, revisions
