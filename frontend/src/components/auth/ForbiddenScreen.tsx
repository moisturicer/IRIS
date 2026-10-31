import { Link } from "react-router-dom";

import { StatusScreen } from "@/components/shared/StatusScreen";
import { PILL_PRIMARY } from "@/components/ui/pillStyles";
import { FOCUS_RING } from "@/components/ui/interaction";
import { pathFor } from "@/lib/access";
import type { RoleName } from "@/lib/constants";
import { cn } from "@/lib/utils";

interface ForbiddenScreenProps {
  authenticatedRole: RoleName | null;
  requiredRoles:     RoleName[];
}

function formatRoles(roles: RoleName[]): string {
  if (roles.length === 0) return "—";
  if (roles.length === 1) return roles[0];
  return roles.slice(0, -1).join(", ") + " or " + roles[roles.length - 1];
}

/**
 * A screen this role cannot open (IR-745).
 *
 * It names both roles because that is what someone asking RDCO for access
 * needs to say. It no longer claims the attempt was "logged to AuditLog":
 * this gate runs in the browser and writes nothing, so that line was untrue.
 * The API is the real boundary, and refuses on its own.
 */
export function ForbiddenScreen({ authenticatedRole, requiredRoles }: ForbiddenScreenProps) {
  return (
    <StatusScreen
      icon="fa-lock"
      title="Access denied"
      message="Your role doesn't open this page. If you need it, ask the Research and Development Coordinating Office."
      code="Error 403"
      actions={
        <Link to={pathFor("discover")} className={cn(PILL_PRIMARY, FOCUS_RING)}>
          Go to Discover
        </Link>
      }
    >
      <dl className="space-y-2 rounded-xl border border-stone-200 bg-surface px-5 py-4 text-small">
        <div className="flex justify-between gap-4">
          <dt className="font-semibold text-stone-600">Your role</dt>
          <dd className="font-medium text-stone-900">{authenticatedRole ?? "None"}</dd>
        </div>
        <div className="flex justify-between gap-4">
          <dt className="font-semibold text-stone-600">Required role</dt>
          <dd className="text-right font-medium text-stone-900">{formatRoles(requiredRoles)}</dd>
        </div>
      </dl>
    </StatusScreen>
  );
}
