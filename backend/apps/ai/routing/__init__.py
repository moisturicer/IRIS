"""Reader-question routing, independent of the answer path (IR-514)."""

from .router import RouteDecision, route_question

__all__ = ["RouteDecision", "route_question"]
