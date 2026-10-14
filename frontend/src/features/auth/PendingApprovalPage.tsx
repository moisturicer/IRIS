/**
 * Shown to a signed-in user who has no role yet. Replaces the app shell: no
 * sidebar, no navigation, only the shared entry frame (IR-537).
 *
 * Every registration creates a role request that RDCO approves or declines,
 * and `role_request` on the user's own payload says which of the two it is
 * still waiting on, so the screen tells pending from declined. It promises no
 * turnaround time: nothing on the server backs one.
 */
import { useId } from "react";
import { useAuth } from "@/hooks/useAuth";
import { authApi } from "@/api/auth";
import { AuthLayout } from "@/components/auth/AuthLayout";
import { Button } from "@/components/ui/Button";
import type { OwnRoleRequest } from "@/types/auth";

/** "a Student", "an Adviser". */
function withArticle(role: string): string {
  return `${/^[aeiou]/i.test(role) ? "an" : "a"} ${role}`;
}

interface Standing {
  title: string;
  message: string;
}

function standingOf(request: OwnRoleRequest | null | undefined, email: string): Standing {
  if (request?.status === "pending") {
    return {
      title: "Waiting for approval",
      message: `RDCO is reviewing your request to join as ${withArticle(request.requested_role)}. You'll get an email at ${email} when they decide.`,
    };
  }
  if (request?.status === "declined") {
    return {
      title: "Request not approved",
      message: `Your request to join as ${withArticle(request.requested_role)} was not approved. Contact RDCO or your department administrator if you think this is a mistake.`,
    };
  }
  // No request: registered without a role, or approved and the role later
  // taken away. Neither "reviewing" nor "declined" would be true.
  return {
    title: "No role assigned",
    message: "Your account doesn't have a role yet, so there is nothing for IRIS to open. Contact RDCO or your department administrator to have one assigned.",
  };
}

export function PendingApprovalPage() {
  const { user, logout, refreshToken } = useAuth();
  const registeredId = useId();

  const handleLogout = async () => {
    try {
      await authApi.logout(refreshToken ?? "");
    } catch {
      // ignore — we log out regardless
    }
    logout();
  };

  // The route guard renders this only for a signed-in user (IR-537).
  if (!user) return null;

  const request = user.role_request;
  const { title, message } = standingOf(request, user.email);

  return (
    <AuthLayout variant="pending">
      <h2 className="text-balance text-display font-bold text-stone-900">{title}</h2>
      <p className="mt-3 text-pretty text-body text-stone-700">{message}</p>

      <div
        role="group"
        aria-labelledby={registeredId}
        className="mt-section-lg border border-stone-200 border-t-2 border-t-gold bg-white px-5 py-4"
      >
        <p id={registeredId} className="text-label font-semibold text-stone-600">
          Registered as
        </p>
        <dl className="mt-3 grid grid-cols-1 gap-x-4 gap-y-2 text-small sm:grid-cols-3">
          <dt className="text-stone-600">Name</dt>
          <dd className="font-semibold text-stone-900 sm:col-span-2">
            {user.first_name} {user.last_name}
          </dd>
          <dt className="mt-1 text-stone-600 sm:mt-0">Email</dt>
          <dd className="break-all text-stone-900 sm:col-span-2">{user.email}</dd>
          {request && (
            <>
              <dt className="mt-1 text-stone-600 sm:mt-0">Requested role</dt>
              <dd className="text-stone-900 sm:col-span-2">{request.requested_role}</dd>
            </>
          )}
        </dl>
      </div>

      <div className="mt-section-lg">
        <Button type="button" variant="outline" size="full" onClick={handleLogout}>
          Sign out
        </Button>
        {request?.status === "pending" && (
          <p className="mt-3 text-center text-small text-stone-600">
            Signing out doesn&apos;t withdraw your request.
          </p>
        )}
      </div>
    </AuthLayout>
  );
}
