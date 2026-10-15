"""Run research-lane tools as a given user, with no model (IR-509, IR-510).

Each `--call` runs through the same registry, run context and ledger a planner
will use, so a handle issued by one call is usable by the next:

    manage.py run_research_tool --user student@cit.edu \
        --call find_records='{"topic": "flooding"}' \
        --call read_record_sections='{"record": "R1"}'

It prints what a planner would be sent, plus the stored pointer behind each
handle. `--general` runs the general-tools contract (IR-591) instead and prints
each call's model-visible envelope:

    manage.py run_research_tool --user student@cit.edu --general \
        --call search_research='{"query": "flooding", "target": "papers"}' \
        --call read_papers='{"records": ["R1-..."], "view": "outline"}'

The disclosure gate in force applies: until IR-250 that withholds all
content unless IR-317's development bypass is on.
"""

from __future__ import annotations

import json

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from apps.ai.composition import composition_root
from apps.ai.conversation_state import current_revision
from apps.ai.models.conversation import Conversation
from apps.ai.research.context import RunContext
from apps.ai.research.registry import ToolRun, general_tools, research_tools


class Command(BaseCommand):
    help = "Run research-lane tools as a user and print what a planner would see."

    def add_arguments(self, parser):
        parser.add_argument("--user", required=True, help="Email of the asking user.")
        parser.add_argument(
            "--call", action="append", required=True, metavar="TOOL=JSON",
            help="A tool and its JSON arguments. Repeatable; one run, in order.",
        )
        parser.add_argument(
            "--conversation", type=int,
            help="A Conversation of this user's; a Paper Chat one scopes the run.",
        )
        parser.add_argument(
            "--general", action="store_true",
            help="Use the five general research tools and print their envelopes.",
        )

    def handle(self, *args, **options):
        user = get_user_model().objects.filter(email=options["user"]).first()
        if user is None:
            raise CommandError(f"No user {options['user']!r}.")

        conversation = None
        if options["conversation"] is not None:
            conversation = Conversation.objects.filter(
                pk=options["conversation"], user=user
            ).first()
            if conversation is None:
                raise CommandError("No such Conversation for this user.")

        calls = [_parse(call) for call in options["call"]]
        root = composition_root()
        ctx = RunContext.for_request(
            user=user, root=root, lane="research", conversation=conversation,
            context_revision=current_revision(conversation),
        )
        general = options["general"]
        run = ToolRun.start(ctx, root, scoped_handles=general)
        registry = general_tools() if general else research_tools()

        for name, arguments in calls:
            if general:
                envelope = registry.invoke(run, name, arguments)
                self.stdout.write(f"== {name} {arguments}")
                self.stdout.write(json.dumps(envelope.public(), indent=2, ensure_ascii=False))
                continue
            result = registry.call(run, name, arguments)
            self.stdout.write(f"== {name} {arguments}")
            self.stdout.write(json.dumps(json.loads(result.planner_message()), indent=2,
                                         ensure_ascii=False))
            for item in result.evidence:
                self.stdout.write(f"   {item.handle} -> {item.pointer}")


def _parse(call: str) -> tuple[str, str]:
    name, sep, arguments = call.partition("=")
    if not sep or not name.strip():
        raise CommandError(f"--call must be TOOL=JSON, got {call!r}.")
    return name.strip(), arguments
