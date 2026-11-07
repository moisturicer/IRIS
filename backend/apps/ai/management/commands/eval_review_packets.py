"""Write one reviewer's packet for a collected run (IR-607). Reads the database, no vendor.

    python manage.py eval_review_packets --run run.json --reviewer EMAIL \\
        --reviewer-name "Name" --out packets.json

Access is `Record.objects.visible_to(reviewer)` now, so a revoked source is
withheld even if the evaluation reader once saw it.

A written packet is a plaintext copy. It is not access control: whoever holds
the file can read it, and `--reviewer` is an argument, not a login. `--reopen`
is the re-check an honest holder runs before reading (IR-721): every turn is
judged by that account's access and its sources' current revisions, another
reviewer's review is replaced by a blank one, and the original is not edited:

    python manage.py eval_review_packets --reopen packets.json --reviewer EMAIL \\
        --reviewer-name "Name" --out reopened.json
"""

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from apps.ai.evaluation.conversations import postdates_lock
from apps.ai.evaluation.review_packets import build_packets, cited_ids, packet_ids, reauthorize
from apps.ai.evaluation.runfile import load_json, write_json
from apps.ai.grants.reads import research_records
from apps.ai.models import ChunkSet


class Command(BaseCommand):
    help = "Write a review packet holding only what one reviewer may read."

    def add_arguments(self, parser):
        parser.add_argument("--run", help="The collected run to package.")
        parser.add_argument("--reopen", help="A written packet to judge again by the "
                            "reviewer's current access, instead of packaging a run.")
        parser.add_argument("--reviewer", required=True, help="The reviewer's login email.")
        parser.add_argument("--reviewer-name", help="The name the reviewer signs reviews with.")
        parser.add_argument("--out", required=True)
        parser.add_argument("--lock", help="The set lock; required for held-out output "
                                           "(with --run).")

    def handle(self, *args, **options):
        if bool(options.get("run")) == bool(options.get("reopen")):
            raise CommandError("give exactly one of --run or --reopen")
        user = get_user_model().objects.filter(email=options["reviewer"]).first()
        if user is None:
            raise CommandError(f"no user {options['reviewer']}")
        if not (options.get("reviewer_name") or "").strip():
            raise CommandError("a reviewer name is required")
        if options.get("reopen"):
            if options.get("lock"):
                raise CommandError("--lock applies to --run only: a written packet was checked "
                                   "against the lock when it was built")
            return self._reopen(user, options)
        run = load_json(options["run"])
        if any(row.get("split") == "held_out" for row in run.get("conversations", ())):
            lock = load_json(options["lock"]) if options["lock"] else {}
            if not postdates_lock((run.get("manifest") or {}).get("timestamp_utc"), lock):
                raise CommandError("held-out output opens only after the lock froze its "
                                   "prompts and rubric; pass --lock and a later run")
        readable, revisions = _access(user, cited_ids(run))
        bundle = build_packets(run, reviewer=options["reviewer_name"].strip(), readable=readable,
                               revisions=revisions)
        self._write(options["out"], bundle, "this reviewer")

    def _reopen(self, user, options):
        written = load_json(options["reopen"])
        readable, revisions = _access(user, packet_ids(written))
        bundle = reauthorize(written, readable=readable, revisions=revisions,
                             reviewer=options["reviewer_name"].strip())
        self._write(options["out"], bundle, "this account")

    def _write(self, out, bundle, whom):
        write_json(out, bundle)
        withheld = sum(t["withheld"] for p in bundle["packets"] for t in p["turns"])
        self.stdout.write(f"wrote {out}: {len(bundle['packets'])} conversations, "
                          f"{withheld} turns withheld from {whom}")


def _access(user, ids):
    """The Records `user` may read among `ids` now, and each one's active source revision."""
    readable = set(research_records(user).filter(pk__in=ids).values_list("pk", flat=True))
    revisions = dict(ChunkSet.objects.filter(record_id__in=readable, is_active=True)
                     .values_list("record_id", "id"))
    return readable, revisions
