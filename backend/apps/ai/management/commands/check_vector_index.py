"""Is vector search finding what it should (IR-442)?

    python manage.py check_vector_index
    python manage.py check_vector_index --titles --user staff@cit.edu

The default compares each index against an exact scan and calls no vendor, so
it is free to run after any corpus load. `--titles` asks the real retrieval
stack about every publicly visible paper by name, at one query embedding per
record, so it is opt-in and never belongs in CI.

A command rather than a test: what is measured is one database's index, and a
test asserting health would pass on an empty test database.
"""

from django.core.management.base import BaseCommand, CommandError

from apps.ai.index_health import (
    DEFAULT_K,
    DEFAULT_MIN_RECALL,
    DEFAULT_PROBES,
    measure_index_recall,
    probe_titles,
)


class Command(BaseCommand):
    help = "Compare the vector indexes against an exact scan, and optionally probe every title."

    def add_arguments(self, parser):
        parser.add_argument(
            "--probes", type=int, default=DEFAULT_PROBES,
            help=f"Stored vectors to use as probes (default {DEFAULT_PROBES}).",
        )
        parser.add_argument(
            "--k", type=int, default=DEFAULT_K,
            help=f"Neighbours compared per probe (default {DEFAULT_K}).",
        )
        parser.add_argument(
            "--min-recall", type=float, default=DEFAULT_MIN_RECALL, dest="min_recall",
            help=f"Exit non-zero below this (default {DEFAULT_MIN_RECALL}).",
        )
        parser.add_argument("--seed", type=int, default=0, help="Sample seed.")
        parser.add_argument(
            "--titles", action="store_true",
            help="Also ask the retrieval stack about every publicly visible "
            "paper by name. COSTS one query embedding per record.",
        )
        parser.add_argument(
            "--user",
            help="Email to retrieve as for --titles. Retrieval is filtered by "
            "visible_to(user), so a paper this user cannot read is a miss.",
        )

    def handle(self, *args, **options):
        from apps.ai.models import EmbeddingSpace, EmbeddingSpaceState
        from apps.ai.models.chunk import ChunkEmbedding
        from apps.ai.models.embedding import RecordEmbedding

        space = EmbeddingSpace.objects.filter(state=EmbeddingSpaceState.ACTIVE).first()
        if space is None:
            raise CommandError(
                "No active EmbeddingSpace: nothing has been indexed, so there "
                "is no index to check."
            )

        self.stdout.write(
            self.style.MIGRATE_HEADING(
                f"\nIndex recall against an exact scan — space {space.pk} ({space.model_id})"
            )
        )

        results = [
            measure_index_recall(
                ChunkEmbedding, space_id=space.pk, k=options["k"],
                probes=options["probes"], seed=options["seed"],
                label="chunk_embedding_hnsw_idx",
            ),
            # Record vectors carry no space column -- one per record -- so no
            # space filter, which is how stage 1 queries them too.
            measure_index_recall(
                RecordEmbedding, k=options["k"], probes=options["probes"],
                seed=options["seed"], label="embedding_hnsw_idx",
            ),
        ]

        failed = False
        for result in results:
            if result.probes == 0:
                self.stdout.write(
                    self.style.WARNING(f"  {result.label}: empty, nothing to check")
                )
                continue
            line = (
                f"  {result.label}: recall@{result.k} {result.recall:.3f} "
                f"over {result.probes} probe(s) at depth {result.depth}"
            )
            if result.recall < options["min_recall"]:
                failed = True
                self.stdout.write(self.style.ERROR(line))
                for probe in result.worst[:5]:
                    self.stdout.write(f"      probe {probe.probe_id}: {probe.recall:.2f}")
            else:
                self.stdout.write(self.style.SUCCESS(line))
            if not result.used_index:
                # Without this the figure above is the index compared with
                # itself, which is 1.000 whatever the index is doing.
                self.stdout.write(
                    self.style.WARNING(
                        "      the planner read no HNSW index here, so this "
                        "number says nothing about it (too few rows?)"
                    )
                )

        if options["titles"]:
            failed = self._probe_titles(options) or failed

        if failed:
            raise CommandError(
                "Vector search is not returning what an exact scan would. "
                "Raise AI_HNSW_EF_SEARCH, or REINDEX the index named above and "
                "re-run."
            )
        self.stdout.write(self.style.SUCCESS("\nVector search looks healthy."))

    def _probe_titles(self, options) -> bool:
        """True if anything was missed."""
        from django.contrib.auth import get_user_model

        from apps.ai.composition import composition_root
        from apps.records.models import PUBLICLY_VISIBLE_STATUSES, Record

        if not options.get("user"):
            raise CommandError(
                "--titles needs --user: retrieval is filtered by "
                "visible_to(user), so the answer depends on who is asking."
            )
        user = get_user_model().objects.filter(email__iexact=options["user"]).first()
        if user is None:
            raise CommandError(f"no user with email {options['user']}")

        records = list(
            Record.objects.filter(pipeline_status__in=PUBLICLY_VISIBLE_STATUSES)
            .order_by("pk")
            .values_list("pk", "title")
        )
        self.stdout.write(
            self.style.MIGRATE_HEADING(
                f"\nTitle probe — {len(records)} paper(s), as {user.email}"
            )
        )
        if not records:
            self.stdout.write(self.style.WARNING("  nothing publicly visible"))
            return False

        retriever = composition_root().retriever()

        def retrieve(question, limit):
            found = retriever.retrieve(question, user, limit=limit)
            return [passage.record_id for passage in found.passages]

        misses = probe_titles(records, retrieve, limit=options["k"])
        if not misses:
            self.stdout.write(
                self.style.SUCCESS(
                    f"  {len(records)} of {len(records)} found by their own title"
                )
            )
            return False

        self.stdout.write(
            self.style.ERROR(
                f"  {len(misses)} of {len(records)} NOT found by their own title:"
            )
        )
        for miss in misses:
            self.stdout.write(f"      record {miss.record_id}: {miss.title[:60]}")
            self.stdout.write(f"          returned instead: {list(miss.returned[:5])}")
        return True
