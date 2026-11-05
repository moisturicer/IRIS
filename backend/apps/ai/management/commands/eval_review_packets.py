"""Write one reviewer's packet for a collected run (IR-607). Reads the database, no vendor.

    python manage.py eval_review_packets --run run.json --reviewer EMAIL \\
        --reviewer-name "Name" --out packets.json

Access is `Record.objects.visible_to(reviewer)` now, so a revoked source is
withheld even if the evaluation reader once saw it.

A written packet is a copy, so holding the file grants nothing (IR-721). Open it
again as whoever is about to read it, and every turn is judged by that account's
access at that moment; the original file is not edited:

    python manage.py eval_review_packets --reopen packets.json --reviewer EMAIL \\
        --out reopened.json
"""

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from apps.ai.evaluation.conversations import postdates_lock
from apps.ai.evaluation.review_packets import build_packets, cited_ids, packet_ids, reauthorize
from apps.ai.evaluation.runfile import load_json, write_json
from apps.ai.grants.reads import research_records


class Command(BaseCommand):
    help = "Write a review packet holding only what one reviewer may read."

    def add_arguments(self, parser):
        parser.add_argument("--run", help="The collected run to package.")
        parser.add_argument("--reopen", help="A written packet to judge again by the "
                            "reviewer's current access, instead of packaging a run.")
        parser.add_argument("--reviewer", required=True, help="The reviewer's login email.")
        parser.add_argument("--reviewer-name",
                            help="The name the reviewer signs reviews with (with --run).")
        parser.add_argument("--out", required=True)
        parser.add_argument("--lock", help="The set lock; required for held-out output.")

    def handle(self, *args, **options):
        if bool(options.get("run")) == bool(options.get("reopen")):
            raise CommandError("give exactly one of --run or --reopen")
        user = get_user_model().objects.filter(email=options["reviewer"]).first()
        if user is None:
            raise CommandError(f"no user {options['reviewer']}")
        if options.get("reopen"):
            return self._reopen(user, options)
        if not (options.get("reviewer_name") or "").strip():
            raise CommandError("a reviewer name is required")
        run = load_json(options["run"])
        if any(row.get("split") == "held_out" for row in run.get("conversations", ())):
            lock = load_json(options["lock"]) if options["lock"] else {}
            if not postdates_lock((run.get("manifest") or {}).get("timestamp_utc"), lock):
                raise CommandError("held-out output opens only after the lock froze its "
                                   "prompts and rubric; pass --lock and a later run")
        readable = research_records(user).filter(
            pk__in=cited_ids(run)).values_list("pk", flat=True)
        bundle = build_packets(run, reviewer=options["reviewer_name"].strip(), readable=readable)
        write_json(options["out"], bundle)
        withheld = sum(t["withheld"] for p in bundle["packets"] for t in p["turns"])
        self.stdout.write(f"wrote {options['out']}: {len(bundle['packets'])} conversations, "
                          f"{withheld} turns withheld from this reviewer")

    def _reopen(self, user, options):
        written = load_json(options["reopen"])
        readable = research_records(user).filter(
            pk__in=packet_ids(written)).values_list("pk", flat=True)
        bundle = reauthorize(written, readable=readable)
        write_json(options["out"], bundle)
        withheld = sum(t["withheld"] for p in bundle["packets"] for t in p["turns"])
        self.stdout.write(f"wrote {options['out']}: {len(bundle['packets'])} conversations, "
                          f"{withheld} turns withheld from this account")
