import { Link } from "react-router-dom";
import { useRole } from "@/hooks/useRole";
import { roleToDiagnosticCode } from "@/lib/roleDisplay";
import type { RoleName } from "@/lib/constants";

interface ForbiddenPageProps {
  /** Roles permitted for the route the user tried to open. */
  requiredRoles: RoleName[];
}

function DiagnosticBadge({
  code,
  variant,
}: {
  code: string;
  variant: "authenticated" | "required";
}) {
  const isRequired = variant === "required";
  return (
    <span
      className={
        isRequired
          ? "inline-block px-3 py-1 rounded-md border border-red-400 bg-white text-red-600 text-[12px] font-mono font-semibold tracking-wide"
          : "inline-block px-3 py-1 rounded-md bg-gray-100 text-gray-700 text-[12px] font-mono font-semibold tracking-wide"
      }
    >
      {code}
    </span>
  );
}

export function ForbiddenPage({ requiredRoles }: ForbiddenPageProps) {
  const { roleName } = useRole();
  const authenticatedCode = roleToDiagnosticCode(roleName);
  const requiredCodes = requiredRoles.map(roleToDiagnosticCode);

  return (
    <div className="flex flex-col items-center justify-center min-h-[calc(100vh-8rem)] px-4 py-12 text-center">
      {/* Icon */}
      <div
        className="relative w-[88px] h-[88px] rounded-full bg-red-50 flex items-center justify-center mb-6"
        aria-hidden
      >
        <i className="fas fa-shield-alt text-[40px] text-red-300" aria-hidden />
        <i className="fas fa-lock text-[18px] text-red-500 absolute bottom-[22px]" aria-hidden />
        <span className="absolute inset-0 flex items-center justify-center pointer-events-none">
          <span className="block w-[70px] h-[3px] bg-red-500 rounded-full rotate-45" />
        </span>
      </div>

      <h1 className="text-[26px] font-bold text-gray-900 tracking-tight mb-3">
        HTTP 403: Access Forbidden
      </h1>
      <p className="text-[14px] text-gray-500 max-w-md mb-8 leading-relaxed">
        You do not have the required role-based permissions to access this workflow tier.
      </p>

      {/* RBAC diagnostic */}
      <div className="w-full max-w-lg border border-dashed border-gray-300 rounded-xl bg-gray-50/80 px-6 py-5 text-left mb-8">
        <p className="text-[13px] font-bold text-gray-800 mb-4">Security &amp; RBAC Diagnostic:</p>

        <div className="flex flex-wrap items-center justify-between gap-2 mb-3">
          <span className="text-[13px] text-gray-600">Authenticated Role:</span>
          <DiagnosticBadge code={authenticatedCode} variant="authenticated" />
        </div>

        <div className="flex flex-wrap items-center justify-between gap-2 mb-4">
          <span className="text-[13px] text-gray-600">Required Role:</span>
          <div className="flex flex-wrap gap-2 justify-end">
            {requiredCodes.map((code) => (
              <DiagnosticBadge key={code} code={code} variant="required" />
            ))}
          </div>
        </div>

        <p className="text-[12px] text-amber-700 font-medium">
          Note: Access violation attempt logged in AuditLog.
        </p>
      </div>

      <Link
        to="/"
        className="inline-flex items-center justify-center px-8 py-3 rounded-lg bg-brand text-white text-[14px] font-semibold hover:bg-brand-light transition-colors shadow-sm"
      >
        Return to Safe Dashboard
      </Link>
    </div>
  );
}
