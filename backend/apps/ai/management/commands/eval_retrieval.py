"""Measure retrieval against a labelled question set (IR-133 / IR-394).

    python manage.py eval_retrieval --questions docs/evaluation/proxy_starter.json --dry-run
    python manage.py eval_retrieval --questions ... --user staff@cit.edu
    python manage.py eval_retrieval --questions ... --user staff@cit.edu --reranking on

**A manual command, never CI** (ADR-023 §Amendment). A real run embeds every
question and reranks every candidate set, so putting it on a push would make
the evaluation budget a function of commit frequency.

`--dry-run` costs nothing and calls no vendor: it checks that every label
resolves against this database. Run it after every few questions while
labelling; a label that does not resolve scores zero for a reason that has
nothing to do with retrieval.

Results are written to `docs/evaluation/runs/` so a number quoted in the thesis
can be traced back to the configuration that produced it.
"""

import json
import os
import subprocess
from pathlib import Path

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from apps.ai.composition import composition_root
from apps.ai.evaluation import (
    QuestionSetError,
    RunConfig,
    check_question_set,
    compare,
    load_question_set,
    render_checks,
    run,
)

DEFAULT_OUT = Path("docs") / "evaluation" / "runs"


def _git_commit() -> str:
    """The commit this run's code came from, for the results file (IR-394).

    ``IRIS_GIT_COMMIT`` wins when set: the command normally runs in a
    container that has no git, so the caller passes it from the host with
    ``-e IRIS_GIT_COMMIT=$(git describe --always --dirty)``. Otherwise git is
    asked, with ``--dirty`` so a run from a modified tree does not read as the
    commit it started from. "unknown" is the answer when nothing can say.
    """
    given = os.environ.get("IRIS_GIT_COMMIT", "").strip()
    if given:
        return given
    try:
        return subprocess.run(
            ["git", "describe", "--always", "--dirty"],
            capture_output=True,
            text=True,
            timeout=5,
        ).stdout.strip() or "unknown"
    except Exception:
        return "unknown"


class Command(BaseCommand):
    help = "Report recall@k and final-set recall for a labelled question set."

    def add_arguments(self, parser):
        parser.add_argument(
            "--questions",
            required=True,
            help="Path to the labelled question set (JSON).",
        )
        parser.add_argument(
            "--user",
            help="Email of the user to retrieve as. Retrieval is filtered by "
            "visible_to(user), so this is part of what is measured. Required "
            "unless --dry-run.",
        )
        parser.add_argument(
            "--reranking",
            choices=["both", "on", "off"],
            default="both",
            help="Which configurations to run (default: both, which is the "
            "comparison IR-133 asks for).",
        )
        parser.add_argument(
            "-k",
            "--limit",
            type=int,
            default=10,
            dest="retrieval_limit",
            help="The k in recall@k (default: 10, per ADR-023).",
        )
        parser.add_argument(
            "--max-sources",
            type=int,
            default=8,
            help="How many passages the model would be given (default: 8, the "
            "answer service's own default).",
        )
        parser.add_argument(
            "--drop-incomplete",
            action="store_true",
            help="Skip questions still holding a TODO instead of refusing the "
            "set, so a partly-labelled set can be measured. The skipped "
            "questions are named in the report and the results file.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Check the labels against this database and stop. No vendor "
            "call, no cost.",
        )
        parser.add_argument(
            "--out",
            default=str(DEFAULT_OUT),
            help=f"Directory for the results file (default: {DEFAULT_OUT}).",
        )
        parser.add_argument(
            "--no-write",
            action="store_true",
            help="Print the report without writing a results file.",
        )

    # -- the command --------------------------------------------------------

    def handle(self, *args, **options):
        try:
            question_set = load_question_set(
                options["questions"], drop_incomplete=options["drop_incomplete"]
            )
        except QuestionSetError as exc:
            raise CommandError(str(exc))

        self.stdout.write(
            f"{question_set.name}: {len(question_set)} questions, "
            f"{question_set.label_count} labels, tier {question_set.tier}"
        )
        if question_set.skipped:
            self.stdout.write(
                self.style.WARNING(
                    f"{len(question_set.skipped)} unlabelled question(s) skipped: "
                    f"{', '.join(question_set.skipped)}"
                )
            )

        if options["dry_run"]:
            checks = check_question_set(question_set)
            self.stdout.write("")
            self.stdout.write(render_checks(checks))
            if any(not c.ok for c in checks):
                raise CommandError("some labels do not resolve")
            self.stdout.write(self.style.SUCCESS("Every label resolves. "))
            return

        user = self._user(options.get("user"))
        self._warn_about_the_gate()

        configs = self._configs(options)
        root = composition_root()
        provenance = {
            "git_commit": _git_commit(),
            "question_set_path": question_set.source,
            "retrieved_as": user.email,
            "disclosure_bypass": bool(
                getattr(settings, "AI_DISCLOSURE_BYPASS_FOR_DEVELOPMENT", False)
            ),
        }

        reports = []
        for config in configs:
            self.stdout.write("")
            self.stdout.write(f"Running {config.label} ...")
            report = run(
                root, question_set, config, user=user, provenance=provenance
            )
            self.stdout.write("")
            self.stdout.write(report.render())
            reports.append(report)

        if len(reports) > 1:
            self.stdout.write("")
            self.stdout.write(compare(reports))

        self._warn_about_empty_final_sets(reports)

        if not options["no_write"]:
            path = self._write(reports, question_set, Path(options["out"]))
            self.stdout.write("")
            self.stdout.write(self.style.SUCCESS(f"Results written to {path}"))

    # -- pieces -------------------------------------------------------------

    def _user(self, email):
        if not email:
            raise CommandError(
                "--user is required: retrieval filters by visible_to(user), so "
                "a run is a measurement of what one user can retrieve. "
                "`manage.py seed_demo` creates <role>@cit.edu logins."
            )
        user = get_user_model().objects.filter(email__iexact=email).first()
        if user is None:
            raise CommandError(f"no user with email {email}")
        return user

    def _configs(self, options):
        choice = options["reranking"]
        wanted = {"both": (False, True), "off": (False,), "on": (True,)}[choice]
        return [
            RunConfig(
                reranking=reranking,
                retrieval_limit=options["retrieval_limit"],
                max_sources=options["max_sources"],
                baseline="no-reranking" if reranking and len(wanted) > 1 else None,
            )
            for reranking in wanted
        ]

    def _warn_about_the_gate(self):
        if getattr(settings, "AI_DISCLOSURE_BYPASS_FOR_DEVELOPMENT", False):
            self.stdout.write(
                self.style.WARNING(
                    "AI_DISCLOSURE_BYPASS_FOR_DEVELOPMENT is on (IR-317). These "
                    "numbers are a development measurement and are not evidence "
                    "about any corpus."
                )
            )

    def _warn_about_empty_final_sets(self, reports):
        for report in reports:
            retrieved = sum(o.retrieved_count for o in report.outcomes)
            final = sum(o.final_count for o in report.outcomes)
            if retrieved and not final:
                self.stdout.write("")
                self.stdout.write(
                    self.style.WARNING(
                        f"{report.config.label}: retrieval returned passages but "
                        f"the model would receive none. That is the disclosure "
                        f"gate refusing every record — `Record` carries no "
                        f"embargo field yet (IR-250). Use "
                        f"AI_DISCLOSURE_BYPASS_FOR_DEVELOPMENT to measure "
                        f"meanwhile."
                    )
                )

    def _write(self, reports, question_set, out_dir: Path) -> Path:
        out_dir.mkdir(parents=True, exist_ok=True)
        stamp = timezone.now().strftime("%Y%m%d-%H%M%S")
        safe = "".join(
            c if c.isalnum() or c in "-_" else "-" for c in question_set.name
        ).strip("-")
        path = out_dir / f"{stamp}-{safe or 'run'}.json"
        path.write_text(
            json.dumps(
                {
                    "runs": [report.as_dict() for report in reports],
                    "baseline": reports[0].config.label,
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        return path
