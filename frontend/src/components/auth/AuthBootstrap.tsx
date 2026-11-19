import { useEffect } from "react";
import { useAuthStore } from "@/store/auth.store";
import { Spinner } from "@/components/ui/Spinner";
import { reloadPage } from "@/lib/readFailure";
import { authApi } from "@/api/auth";
import { startHeartbeat, startIdleWatch, trackActivity } from "@/lib/activity";
import { redirectToLoginSessionExpired } from "@/lib/authSession";
import { startLive, stopLive } from "@/lib/live";
import { refreshSession } from "@/api/client";

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
  const remembered      = useAuthStore((s) => s.remembered);

  useEffect(() => {
    void hydrateAuth();
  }, [hydrateAuth]);

  useEffect(() => trackActivity(window), []);

  useEffect(() => {
    if (!isAuthenticated) return;
    // "Keep me signed in" (ADR-072): the server doesn't end a remembered
    // session for idleness, so neither does the browser.
    const unwatch = remembered ? () => {} : startIdleWatch(() => {
      useAuthStore.getState().logout();
      redirectToLoginSessionExpired();
    });
    // The server judges idleness from the activity requests have reported, so
    // reading a page that sends nothing still has to be heard. A 401 here is
    // handled by the client's interceptor like any other.
    const stopHeartbeat = startHeartbeat(() => { void authApi.me().catch(() => {}); });
    return () => { unwatch(); stopHeartbeat(); };
  }, [isAuthenticated, remembered]);

  // Live updates (ADR-073): one hint stream per tab while signed in, opened
  // with the current access token and refreshed through the one refresh path.
  useEffect(() => {
    if (!isAuthenticated) return;
    startLive({ token: () => useAuthStore.getState().accessToken, refresh: refreshSession });
    return () => stopLive();
  }, [isAuthenticated]);

  if (!authReady) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-canvas">
        <Spinner size="lg" label="Loading IRIS" onRetry={reloadPage} />
      </div>
    );
  }

  return <>{children}</>;
}
