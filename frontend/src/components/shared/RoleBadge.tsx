import { Badge } from "@/components/ui/Badge";

type BadgeVariantType = Parameters<typeof Badge>[0]["variant"];

const ROLE_VARIANT: Record<string, BadgeVariantType> = {
  Student:  "info",
  Adviser:  "success",
  KTTO:     "warning",
  RDCO:     "warning",
  ITSO:     "neutral",
  IERC:     "neutral",
};

interface RoleBadgeProps {
  role: string;
}

export function RoleBadge({ role }: RoleBadgeProps) {
  return <Badge variant={ROLE_VARIANT[role] ?? "default"}>{role}</Badge>;
}
