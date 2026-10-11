"""Request-owned dispatch and metadata for the development research lane."""
from dataclasses import asdict, dataclass
from typing import ClassVar

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured

from apps.ai.answers.citations import GroundedAnswer, NO_SOURCES
from apps.ai.answers.events import AnswerEvent
from .configuration import configured_providers
from .router import LANES, route_question


def verify_research_configuration():
    if settings.AI_RESEARCH_LANE not in ("off", "on"):
        raise ImproperlyConfigured("AI_RESEARCH_LANE must be off or on")
    if settings.AI_RESEARCH_LANE == "on" and not settings.DEBUG:
        raise ImproperlyConfigured("AI_RESEARCH_LANE is development-only until IR-504")


@dataclass(frozen=True)
class RoutingDecided(AnswerEvent):
    routing: dict
    name: ClassVar[str] = "routing_decided"


class RoutedChat:
    def __init__(self, asked, *, root, max_sources):
        self.asked = asked
        self.root = root
        self.max_sources = max_sources
        self.decision = None
        self.listing = None

    @property
    def metadata(self):
        if self.decision is None:
            return {}
        return {"routing": self.decision, **({"listing": self.listing} if self.listing else {})}

    @property
    def nonpassage(self):
        return self.decision is not None and self.decision["lane"] != "passage"

    def decide(self, user):
        if self.decision is not None or settings.AI_RESEARCH_LANE == "off":
            return
        asked = self.asked
        jev, backup = configured_providers(root=self.root)
        result = route_question(
            asked.question, resolved_question=asked.resolved_question,
            prior_reader_questions=[turn.question for turn in asked.history],
            paper_chat=asked.scope_record is not None, widened=asked.widened,
            jev=jev, backup=backup,
            uncertain_band=(settings.AI_ROUTE_UNCERTAIN_MIN, settings.AI_ROUTE_UNCERTAIN_MAX),
            injection_threshold=settings.AI_ROUTE_INJECTION_THRESHOLD, audit_user=user,
        )
        decision = asdict(result)
        allowed = list(LANES)
        lane = result.lane
        # Reader overrides cannot bypass question screening or Paper Chat scope.
        if result.suggested_lane == "landscape":
            lane, allowed = "landscape", ["landscape"]
        elif result.injection_flagged or asked.scope_record is not None:
            allowed = ["passage"]
        override = asked.route_override
        if override in allowed:
            lane = override
        decision.update(lane=lane, override=override,
                        override_applied=override is not None and override in allowed,
                        allowed_overrides=allowed,
                        planner_allowed=lane == "research" and not result.injection_flagged)
        self.decision = decision

    def answer(self, user):
        self.decide(user)
        if not self.nonpassage:
            return None
        if self.decision["lane"] == "landscape":
            return GroundedAnswer(
                text="IRIS cannot provide a research landscape or gap analysis until the research-landscape capability is available. Retrieved passages cannot establish comprehensive coverage.",
                citations=(), state=NO_SOURCES,
            )
        from .lanes import answer_lane

        answer, self.listing = answer_lane(
            self.decision["lane"], self.asked.effective_question, user,
            root=self.root, conversation=self.asked.conversation,
            scope_record=self.asked.scope_record, max_sources=self.max_sources,
        )
        return answer
