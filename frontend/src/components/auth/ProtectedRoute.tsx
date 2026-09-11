import { useEffect, useRef, useState } from "react";
import { Navigate, Outlet, useLocation } from "react-router-dom";
import type { RoleName } from "@/lib/constants";
import type { User } from "@/types/auth";
import { useAuthStore } from "@/store/auth.store";
import { decodeJwtPayload, isJwtExpired } from "@/lib/jwt";
import { wholePath } from "@/lib/redirectTarget";
import { ForbiddenScreen } from "./ForbiddenScreen";
import { Spinner } from "@/components/ui/Spinner";

interface ProtectedRouteProps {
  allowedRoles: RoleName[];
}

function resolveRoleName(token: string, user: User | null): RoleName | null {
  const payload = decodeJwtPayload(token);
  if (!payload) return null;

  if (payload.role_id != null && user?.role === payload.role_id && user.role_name) {
    return user.role_name;
  }

  return user?.role_name ?? null;
}

function isDjangoStaff(user: User | null): boolean {
  return user?.is_staff === true || user?.is_superuser === true;
}

/**
 * Route guard — validates JWT and enforces client-side RBAC (UX only).
 * Real enforcement is on the Django API (NFR-S4).
 */
export function ProtectedRoute({ allowedRoles }: ProtectedRouteProps) {
  const accessToken = useAuthStore((s) => s.accessToken);
  const user        = useAuthStore((s) => s.user);
  const authReady     = useAuthStore((s) => s.authReady);
  const location      = useLocation();
  /**
   * Sticky, and it has to be.
   *
   * The expired branch below calls `logout()`, which clears the token and
   * re-renders this guard *before* the redirect it returned has committed. On
   * that second render there is no token at all, so without remembering the
   * decision the guard falls into the "never signed in" branch and the
   * session-expired reason is destroyed on its way to the login screen — the
   * user is silently returned to sign-in with no explanation. A ref survives
   * the re-render; the store, by definition, does not.
   */
  const sessionExpired = useRef(false);
  /**
   * A live region that is inserted *already* carrying its text is generally not
   * announced -- NVDA and JAWS announce changes to a region they were already
   * observing. `Skeleton` (IR-158) documents this and solves it the same way:
   * paint the region empty, fill it on the next tick, and the mutation is what
   * gets read out.
   */
  const [announceWait, setAnnounceWait] = useState(false);
  useEffect(() => setAnnounceWait(true), []);

  if (!authReady) {
    return (
      <div
        role="status"
        aria-live="polite"
        aria-busy="true"
        className="flex min-h-[40vh] items-center justify-center"
      >
        {/*
          The spinner is `aria-hidden` decoration, so without this span the
          waiting state is a blank, silent page -- indistinguishable from one
          that failed to load. The text is the announcement; matching
          `Skeleton`'s wording keeps every wait in the product sounding alike.
        */}
        <span className="sr-only">{announceWait ? "Loading…" : ""}</span>
        <Spinner size="md" />
      </div>
    );
  }

  // The page they actually asked for, kept whole. `LoginPage` validates this
  // before acting on it (`lib/redirectTarget.ts`); it travels in router state
  // rather than the URL so the common case never puts a redirect target
  // somewhere it can be edited (IR-236).
  const attempted = wholePath(location);

  if (accessToken) {
    const payload = decodeJwtPayload(accessToken);
    if (!payload || isJwtExpired(payload)) {
      sessionExpired.current = true;
      useAuthStore.getState().logout();
    } else {
      // Cleared on every valid token, so the flag cannot latch: a render that
      // momentarily saw an expired token -- one racing the silent refresh in
      // `api/client.ts`, say -- must not pin this guard to "session expired"
      // for the life of the mount.
      sessionExpired.current = false;
    }
  }

  // Checked before the "no token" branch, because by the time this re-renders
  // `logout()` has made those two states look identical.
  if (sessionExpired.current) {
    // An expired session keeps its own reason -- it earns a "you were signed
    // out" message that an absent session must not show -- and carries the
    // destination too, so the banner and the return trip are independent.
    return (
      <Navigate to="/login" replace state={{ reason: "session_expired", from: attempted }} />
    );
  }

  if (!accessToken) {
    return <Navigate to="/login" replace state={{ from: attempted }} />;
  }

  if (isDjangoStaff(user)) {
    return <Outlet />;
  }

  const roleName = resolveRoleName(accessToken, user);
  if (!roleName || !allowedRoles.includes(roleName)) {
    return (
      <ForbiddenScreen
        authenticatedRole={roleName ?? user?.role_name ?? null}
        requiredRoles={allowedRoles}
      />
    );
  }

  return <Outlet />;
}
