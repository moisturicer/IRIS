"""Exercise the research planner offline as one reader (IR-512)."""

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from apps.ai.composition import composition_root
from apps.ai.models import Conversation
from apps.ai.research.context import RunContext
from apps.ai.research.planner import ResearchPlanner


class Command(BaseCommand):
    help = "Run the bounded research planner as a user, printing steps and the cited answer."

    def add_arguments(self, parser):
        parser.add_argument("question")
        parser.add_argument("--user", required=True, help="Email of the asking user.")
        parser.add_argument("--conversation", type=int)

    def handle(self, *args, **options):
        user = get_user_model().objects.filter(email=options["user"]).first()
        if user is None:
            raise CommandError("No such user.")
        conversation = None
        if options["conversation"] is not None:
            conversation = Conversation.objects.owned_by(user).filter(pk=options["conversation"]).first()
            if conversation is None:
                raise CommandError("No such Conversation for this user.")
        root = composition_root()
        ctx = RunContext.for_request(user=user, root=root, conversation=conversation, lane="research")
        result = ResearchPlanner(root).answer(options["question"], ctx)
        self.stdout.write(f"Run {result.run_id}: {result.stop_reason}")
        for index, step in enumerate(result.steps, 1):
            duplicate = " duplicate" if step.duplicate else ""
            self.stdout.write(f"{index}. {step.kind} {step.tool}: {step.status}{duplicate} ({step.latency_ms} ms)")
        self.stdout.write(result.answer.text)
        for citation in result.answer.citations:
            handle = result.source_handles.get(citation.marker, "pipeline")
            self.stdout.write(f"[{citation.marker}] {handle}: {citation.record_title}, page {citation.source_page}")
        if result.validation_codes:
            self.stdout.write("Validation: " + ", ".join(result.validation_codes))
