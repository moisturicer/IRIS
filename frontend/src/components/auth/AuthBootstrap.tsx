import { useEffect } from "react";
import { useAuthStore } from "@/store/auth.store";
import { Spinner } from "@/components/ui/Spinner";

/**
 * Restores the session from sessionStorage (refresh token) before the router
 * evaluates protected routes, so a hard refresh on /admin/users shows 403
 * instead of bouncing to login.
 */
export function AuthBootstrap({ children }: { children: React.ReactNode }) {
  const authReady   = useAuthStore((s) => s.authReady);
  const hydrateAuth = useAuthStore((s) => s.hydrateAuth);

  useEffect(() => {
    void hydrateAuth();
  }, [hydrateAuth]);

  if (!authReady) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gray-100">
        <Spinner size="lg" />
      </div>
    );
  }

  return <>{children}</>;
}
