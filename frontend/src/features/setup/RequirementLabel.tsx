import { Badge } from "@/components/ui/Badge";

/**
 * A requirement's label (ADR-063 decision 3): Required or Optional. It tells
 * people what RDCO expects and never blocks submitting. Setup and Guidelines
 * show the same one.
 */
export function RequirementLabel({ required }: { required: boolean }) {
  return <Badge variant={required ? "warning" : "neutral"}>{required ? "Required" : "Optional"}</Badge>;
}
