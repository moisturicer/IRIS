import type { RoutingDecision } from "@/types/ai";

export const routingFixture: RoutingDecision = {
  lane: "passage", suggested_lane: "passage", stage: "rule",
  reason: "confident",
  injection_flagged: false, planner_allowed: true,
  probabilities: {}, override: null, override_applied: false,
  allowed_overrides: ["passage", "listing", "count"],
};
