"""Write one reviewer's packet for a collected run (IR-607). Reads the database, no vendor.

    python manage.py eval_review_packets --run run.json --reviewer EMAIL \\
        --reviewer-name "Name" --out packets.json

Access is `Record.objects.visible_to(reviewer)` now, so a revoked source is
withheld even if the evaluation reader once saw it.
"""

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from apps.ai.evaluation.conversations import postdates_lock
from apps.ai.evaluation.review_packets import build_packets, cited_ids
from apps.ai.evaluation.runfile import load_json, write_json
from apps.records.models import Record


class Command(BaseCommand):
    help = "Write a review packet holding only what one reviewer may read."

    def add_arguments(self, parser):
        parser.add_argument("--run", required=True)
        parser.add_argument("--reviewer", required=True, help="The reviewer's login email.")
        parser.add_argument("--reviewer-name", required=True,
                            help="The name the reviewer signs reviews with.")
        parser.add_argument("--out", required=True)
        parser.add_argument("--lock", help="The set lock; required for held-out output.")

    def handle(self, *args, **options):
        user = get_user_model().objects.filter(email=options["reviewer"]).first()
        if user is None:
            raise CommandError(f"no user {options['reviewer']}")
        if not options["reviewer_name"].strip():
            raise CommandError("a reviewer name is required")
        run = load_json(options["run"])
        if any(row.get("split") == "held_out" for row in run.get("conversations", ())):
            lock = load_json(options["lock"]) if options["lock"] else {}
            if not postdates_lock((run.get("manifest") or {}).get("timestamp_utc"), lock):
                raise CommandError("held-out output opens only after the lock froze its "
                                   "prompts and rubric; pass --lock and a later run")
        readable = Record.objects.visible_to(user).filter(
            pk__in=cited_ids(run)).values_list("pk", flat=True)
        bundle = build_packets(run, reviewer=options["reviewer_name"].strip(), readable=readable)
        write_json(options["out"], bundle)
        withheld = sum(t["withheld"] for p in bundle["packets"] for t in p["turns"])
        self.stdout.write(f"wrote {options['out']}: {len(bundle['packets'])} conversations, "
                          f"{withheld} turns withheld from this reviewer")
