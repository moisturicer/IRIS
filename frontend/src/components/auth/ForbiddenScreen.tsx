import { Link } from "react-router-dom";
import type { RoleName } from "@/lib/constants";

interface ForbiddenScreenProps {
  authenticatedRole: RoleName | null;
  requiredRoles:     RoleName[];
}

function formatRoles(roles: RoleName[]): string {
  if (roles.length === 0) return "—";
  if (roles.length === 1) return roles[0];
  return roles.slice(0, -1).join(", ") + " or " + roles[roles.length - 1];
}

/** RBAC forbidden UI — SRS wireframe Figure 53. */
export function ForbiddenScreen({ authenticatedRole, requiredRoles }: ForbiddenScreenProps) {
  return (
    <div className="flex min-h-[60vh] items-center justify-center px-4">
      <div className="w-full max-w-lg rounded-xl border border-red-200 bg-white p-8 text-center shadow-sm">
        <div className="mx-auto mb-4 flex h-16 w-16 items-center justify-center rounded-full bg-red-100 text-[#8B1A1A]">
          <i className="fas fa-shield-alt text-2xl" aria-hidden />
        </div>
        <h1 className="text-[22px] font-bold text-gray-900">403 — Access Denied</h1>
        <p className="mt-2 text-[14px] text-gray-600">
          You do not have permission to view this page.
        </p>

        <dl className="mt-6 space-y-3 rounded-lg bg-gray-50 px-5 py-4 text-left text-[13px]">
          <div className="flex justify-between gap-4">
            <dt className="font-semibold text-gray-500">Your role</dt>
            <dd className="font-medium text-gray-900">{authenticatedRole ?? "Unknown"}</dd>
          </div>
          <div className="flex justify-between gap-4">
            <dt className="font-semibold text-gray-500">Required role</dt>
            <dd className="font-medium text-gray-900 text-right">{formatRoles(requiredRoles)}</dd>
          </div>
        </dl>

        <p className="mt-5 text-[12px] font-medium text-[#8B1A1A]">
          Access violation attempt logged to AuditLog.
        </p>

        <Link
          to="/"
          className="mt-6 inline-flex items-center gap-2 rounded-lg bg-[#8B1A1A] px-5 py-2.5 text-[13px] font-semibold text-white hover:bg-[#6B0F12] transition-colors"
        >
          <i className="fas fa-home text-[12px]" aria-hidden />
          Return to Dashboard
        </Link>
      </div>
    </div>
  );
}
