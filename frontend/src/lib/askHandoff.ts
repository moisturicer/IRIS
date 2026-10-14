/**
 * Handing a question to Ask IRIS as an editable draft (IR-559).
 *
 * The question travels in router state, not the URL: it is not retained in
 * history entries a reader shares or bookmarks, and nothing is sent until the
 * reader presses Send on the other side.
 */
import { useLocation, useNavigate, useSearchParams } from "react-router-dom";
import { useCallback, useEffect, useState } from "react";

export const ASK_PATH = "/ai";

interface HandoffState {
  draft?: unknown;
}

/** Navigates to Ask IRIS carrying `question` as a draft. */
export function useAskIrisHandoff() {
  const navigate = useNavigate();
  return useCallback(
    (question: string) => navigate(ASK_PATH, { state: { draft: question } satisfies HandoffState }),
    [navigate],
  );
}

/**
 * The draft handed to this page, read once on arrival: from router state, or
 * from a legacy `?q=` link. Either way it is stripped from the address and
 * history entry so a reload or a shared link cannot replay it.
 */
export function useConsumeHandoff(): string | null {
  const location = useLocation();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();

  const [draft] = useState<string | null>(() => {
    const fromState = (location.state as HandoffState | null)?.draft;
    const legacy = searchParams.get("q");
    const text = typeof fromState === "string" ? fromState : legacy;
    return text && text.trim() ? text : null;
  });

  useEffect(() => {
    if (location.state == null && !searchParams.has("q")) return;
    const next = new URLSearchParams(searchParams);
    next.delete("q");
    const search = next.toString();
    navigate(
      { pathname: location.pathname, search: search ? `?${search}` : "" },
      { replace: true, state: null },
    );
    // Runs once, on arrival: the draft is already captured above.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return draft;
}
