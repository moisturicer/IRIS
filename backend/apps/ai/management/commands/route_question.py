"""Demonstrate IR-514's router before it is wired to a reader request."""

from __future__ import annotations

import json
from dataclasses import asdict

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from apps.ai.routing import route_question
from apps.ai.routing.configuration import configured_providers


class Command(BaseCommand):
    help = "Route one reader question and print the lane, probabilities and stage."

    def add_arguments(self, parser):
        parser.add_argument("question")
        parser.add_argument("--resolved-question", default=None)
        parser.add_argument("--prior-question", action="append", default=[])
        parser.add_argument("--paper-chat", action="store_true")
        parser.add_argument("--widened", action="store_true")
        parser.add_argument("--user", help="Existing reader email; logs a flagged question")

    def handle(self, *args, **options):
        user = None
        if options["user"]:
            from apps.accounts.models import User

            user = User.objects.filter(email=options["user"]).first()
            if user is None:
                raise CommandError("No reader has that email")
        jev, backup = configured_providers()
        decision = route_question(
            options["question"],
            resolved_question=options["resolved_question"],
            prior_reader_questions=options["prior_question"],
            paper_chat=options["paper_chat"],
            widened=options["widened"],
            jev=jev,
            backup=backup,
            uncertain_band=(
                settings.AI_ROUTE_UNCERTAIN_MIN, settings.AI_ROUTE_UNCERTAIN_MAX
            ),
            injection_threshold=settings.AI_ROUTE_INJECTION_THRESHOLD,
            audit_user=user,
        )
        self.stdout.write(json.dumps(asdict(decision), sort_keys=True))
