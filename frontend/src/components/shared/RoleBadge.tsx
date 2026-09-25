import { Badge } from "@/components/ui/Badge";

interface RoleBadgeProps {
  role: string;
}

// A role is not a state, so it takes no status tone (IR-359): Badge's variants
// now mean settled, attention and so on, and the old per-role hues had put an
// Adviser in the "finished" black. Every role reads quiet; its name tells them
// apart.
export function RoleBadge({ role }: RoleBadgeProps) {
  return <Badge>{role}</Badge>;
}
