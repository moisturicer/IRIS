import { useEffect } from "react";
import { useAuthStore } from "@/store/auth.store";
import { Spinner } from "@/components/ui/Spinner";
import { authApi } from "@/api/auth";
import { startHeartbeat, startIdleWatch, trackActivity } from "@/lib/activity";
import { redirectToLoginSessionExpired } from "@/lib/authSession";

/**
 * Restores the session from sessionStorage (refresh token) before the router
 * evaluates protected routes, so a hard refresh on /admin/users shows 403
 * instead of bouncing to login.
 *
 * Also the interface's half of the 30-minute inactivity rule (IR-166): it
 * listens for input for the whole app, and while someone is signed in it signs
 * them out when they have been idle that long. The redirect is a full page
 * load, so nothing the screen showed survives it.
 */
export function AuthBootstrap({ children }: { children: React.ReactNode }) {
  const authReady       = useAuthStore((s) => s.authReady);
  const hydrateAuth     = useAuthStore((s) => s.hydrateAuth);
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated);

  useEffect(() => {
    void hydrateAuth();
  }, [hydrateAuth]);

  useEffect(() => trackActivity(window), []);

  useEffect(() => {
    if (!isAuthenticated) return;
    const unwatch = startIdleWatch(() => {
      useAuthStore.getState().logout();
      redirectToLoginSessionExpired();
    });
    // The server judges idleness from the activity requests have reported, so
    // reading a page that sends nothing still has to be heard. A 401 here is
    // handled by the client's interceptor like any other.
    const stopHeartbeat = startHeartbeat(() => { void authApi.me().catch(() => {}); });
    return () => { unwatch(); stopHeartbeat(); };
  }, [isAuthenticated]);

  if (!authReady) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gray-100">
        <Spinner size="lg" />
      </div>
    );
  }

  return <>{children}</>;
}
