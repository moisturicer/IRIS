import { useCallback, useEffect } from "react";

import { useAuthStore } from "@/store/auth.store";
import { useLibraryStore } from "@/store/library.store";

/**
 * Load the signed-in reader's library once per session (IR-566).
 *
 * Keyed on `sessionEpoch` and `isAuthenticated`, so a reload that restores a
 * session, a sign-in and an account switch each load the right account's
 * saves. The store itself drops anything that answers for an older session.
 */
export function useLibrary() {
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated);
  const sessionEpoch = useAuthStore((s) => s.sessionEpoch);
  const load = useLibraryStore((s) => s.load);
  const interrupted = useLibraryStore((s) => s.interrupted);
  const ensureLoaded = useLibraryStore((s) => s.ensureLoaded);

  useEffect(() => {
    if (isAuthenticated) void ensureLoaded();
  }, [isAuthenticated, sessionEpoch, ensureLoaded]);

  const retry = useCallback(() => void ensureLoaded(true), [ensureLoaded]);
  return { load, interrupted, retry };
}
