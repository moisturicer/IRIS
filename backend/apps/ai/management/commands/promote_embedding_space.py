"""Make an Embedding Space live, once it is verified -- or return to the one before
(IR-282, IR-739).

    python manage.py promote_embedding_space --space 3 --check
    python manage.py promote_embedding_space --space 3 --dry-run
    python manage.py promote_embedding_space --space 3 --probe-user reader@cit.edu
    python manage.py promote_embedding_space --rollback --dry-run
    python manage.py promote_embedding_space --rollback
    python manage.py promote_embedding_space --reopen-rollback-target

**Separate from the backfill on purpose.** Promotion is the decision that a
space is ready to answer questions; folding it into the run that fills the
space would make it a side effect of finishing, and "finishing" includes
finishing badly. A space that goes active half-indexed answers confidently from
the half it holds, and a chunk with no vector does not rank low -- it is simply
not there, invisibly.

So this verifies the whole Record-and-Passage pair (coverage, widths,
query/document semantics, current revisions, index health), says every reason it
refuses, and only then flips both levels in one transaction. ``--check`` and
``--dry-run`` change nothing and call no vendor; ``--check`` always exits 0,
``--dry-run`` exits non-zero when the move would be refused. Nothing promotes
automatically, and running this is a deliberate operational act: it does not
build a space (``backfill_embeddings --space``) and does not deploy anything.
"""

import json

from django.core.management.base import BaseCommand, CommandError

from apps.ai.promotion import PromotionRefused, records_missing_vectors


class Command(BaseCommand):
    help = (
        "Verify and promote a pending EmbeddingSpace to active, or roll back to "
        "the previous revision. Refuses, naming every reason, if it is not ready."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--space", type=int, dest="space_id", default=None,
            help="The EmbeddingSpace id to promote (required unless --rollback).",
        )
        parser.add_argument(
            "--check", action="store_true",
            help="Report readiness and stop. Nothing is changed; exits 0.",
        )
        parser.add_argument(
            "--dry-run", action="store_true", dest="dry_run",
            help="Run the full verification and stop. Nothing is changed; exits "
            "non-zero when the move would be refused.",
        )
        parser.add_argument(
            "--rollback", action="store_true",
            help="Return to the space the last promotion replaced. Applies the "
            "same verification, against today's corpus.",
        )
        parser.add_argument(
            "--reopen-rollback-target", action="store_true", dest="reopen",
            help="Return the rollback target to pending so `backfill_embeddings "
            "--space N` can catch it up before a rollback. Deletes nothing.",
        )
        parser.add_argument(
            "--probe-user", dest="probe_user", default=None,
            help="Email to search as before and after: stored vectors are the "
            "queries (no vendor call) and every cited passage must be a current "
            "one this user may read.",
        )
        parser.add_argument(
            "--skip-index-check", action="store_true", dest="skip_index",
            help="Skip the HNSW recall comparison (it is slow on a large corpus).",
        )
        parser.add_argument(
            "--actor", default="",
            help="Who is doing this; recorded in the activation history.",
        )
        parser.add_argument(
            "--json", action="store_true", dest="as_json",
            help="Print the result as one JSON document instead of prose.",
        )
        parser.add_argument(
            "--show", type=int, default=20,
            help="How many short records to list (default 20).",
        )

    def handle(self, *args, **options):
        from apps.ai.models import EmbeddingSpace, EmbeddingSpaceState
        from apps.ai.space_activation import (
            activate_space,
            check_activation,
            reopen_rollback_target,
            rollback_target,
        )

        if options["reopen"]:
            try:
                reopened = reopen_rollback_target()
            except PromotionRefused as exc:
                raise CommandError(str(exc)) from exc
            self.stdout.write(self.style.SUCCESS(
                f"Space {reopened.pk} is pending again. Build it with "
                f"`backfill_embeddings --space {reopened.pk}`, then `--rollback`."))
            return

        kind = "rollback" if options["rollback"] else "promote"
        if kind == "rollback":
            space = rollback_target()
            if space is None:
                raise CommandError("There is no previous revision recorded to roll back to.")
            if options["space_id"] not in (None, space.pk):
                raise CommandError(
                    f"Space {options['space_id']} is not the previous revision; a rollback "
                    f"returns only to space {space.pk}.")
        else:
            if options["space_id"] is None:
                raise CommandError("--space is required (or use --rollback).")
            space = EmbeddingSpace.objects.filter(pk=options["space_id"]).first()
            if space is None:
                raise CommandError(f"No EmbeddingSpace with id {options['space_id']}.")

        if not options["as_json"]:
            self.stdout.write(self.style.MIGRATE_HEADING(
                f"\nEmbeddingSpace {space.pk}: {space} ({kind})"))
            self._write_shortfalls(space, options["show"])
            self._write_readiness(space.pk)

        verdict = check_activation(space, kind=kind, verify_index=not options["skip_index"])
        probe_user = self._probe_user(options["probe_user"])
        probes = {}
        if probe_user is not None:
            probes["before"] = self._probe(probe_user)

        if options["check"] or options["dry_run"]:
            if options["as_json"]:
                self.stdout.write(json.dumps(
                    {"dry_run": True, "verdict": verdict.as_dict(), "probes": probes}, indent=2))
            else:
                self._write_verdict(verdict)
                self._write_probes(probes)
            if options["dry_run"] and not verdict.ok:
                raise CommandError(f"Would be refused: {verdict.message()}")
            return

        if space.state == EmbeddingSpaceState.ACTIVE:
            self.stdout.write(self.style.WARNING("\nAlready active. Nothing to do."))
            return

        try:
            result = activate_space(
                space.pk, kind=kind, actor=options["actor"],
                expect_active=verdict.current_active_id,
                verify_index=not options["skip_index"],
            )
        except PromotionRefused as exc:
            if not options["as_json"]:
                self._write_verdict(getattr(exc, "verdict", verdict))
            raise CommandError(
                f"{exc} Run `backfill_embeddings` until this reports clean, then "
                f"promote again.") from exc

        if probe_user is not None:
            probes["after"] = self._probe(probe_user, space=space)
        if options["as_json"]:
            self.stdout.write(json.dumps({**result.as_dict(), "probes": probes}, indent=2))
        else:
            self._write_verdict(result.verdict)
            self._write_probes(probes)
            self.stdout.write(self.style.SUCCESS(
                f"\n{'Rolled back to' if kind == 'rollback' else 'Promoted'} space {space.pk}. "
                f"Space {result.previous_space_id} is retired, not deleted, and is the "
                f"target of `--rollback`."))
        if any(not p["ok"] for p in probes.values()):
            raise CommandError("The reader probe reported a problem; see above.")

    # -- output --------------------------------------------------------------

    def _write_shortfalls(self, space, show):
        shortfalls = records_missing_vectors(space.pk)
        if shortfalls:
            self.stdout.write(self.style.ERROR(
                f"  {len(shortfalls)} record(s) have active chunks with no "
                f"vector in this space:"))
            for short in shortfalls[:show]:
                self.stdout.write(
                    f"      record {short.record_id}: {short.missing} of "
                    f"{short.total} chunk(s) short — {short.title[:60]}")
            if len(shortfalls) > show:
                self.stdout.write(f"      … and {len(shortfalls) - show} more")
        else:
            self.stdout.write(self.style.SUCCESS("  every active chunk has a vector"))

    def _write_verdict(self, verdict):
        self.stdout.write("  verification:")
        for key, value in sorted(verdict.checks.items()):
            self.stdout.write(f"      {key} = {value}")
        if verdict.ok:
            self.stdout.write(self.style.SUCCESS("  verdict             ready to go live"))
        else:
            self.stdout.write(self.style.ERROR("  verdict             would be refused:"))
            for refusal in verdict.refusals:
                self.stdout.write(self.style.ERROR(f"      [{refusal.code}] {refusal.detail}"))

    def _probe_user(self, email):
        if not email:
            return None
        from django.contrib.auth import get_user_model

        user = get_user_model().objects.filter(email__iexact=email).first()
        if user is None:
            raise CommandError(f"no user with email {email}")
        return user

    def _probe(self, user, space=None):
        from apps.ai.record_vectors import active_space
        from apps.ai.space_activation import reader_probe

        target = space or active_space()
        if target is None:
            return {"space_id": None, "probes": 0, "passages_returned": 0,
                    "own_chunk_found": 0, "failures": [], "ok": True}
        return reader_probe(target, user)

    def _write_probes(self, probes):
        for when, probe in probes.items():
            line = (f"  reader probe {when:<6} space {probe['space_id']}: {probe['probes']} search(es), "
                    f"{probe['passages_returned']} citation(s) checked, "
                    f"{len(probe['failures'])} problem(s)")
            self.stdout.write(self.style.SUCCESS(line) if probe["ok"] else self.style.ERROR(line))
            for failure in probe["failures"][:5]:
                self.stdout.write(f"      {failure}")

    def _write_readiness(self, space_id):
        """Summary and dimension coverage beside the passage shortfall (IR-752).

        Reporting only: the verification below is what activation enforces.
        """
        from apps.ai.space_build import space_readiness

        r = space_readiness(space_id)
        self.stdout.write(
            f"  summary vectors     {r.summaries_built} current of {r.records_total} "
            f"record(s); {r.summaries_missing} missing, {r.summaries_stale} stale, "
            f"{r.summaries_unverified} unverified"
        )
        self.stdout.write(
            f"  passage vectors     {r.passages_embedded} of {r.passages_total}"
        )
        line = f"  dimension check     {r.dimension_mismatches} mismatch(es)"
        self.stdout.write(
            self.style.SUCCESS(line) if not r.dimension_mismatches else self.style.ERROR(line)
        )
        verdict = "complete and current" if r.ready else "not ready"
        self.stdout.write(
            (self.style.SUCCESS if r.ready else self.style.WARNING)(f"  coverage            {verdict}")
        )
