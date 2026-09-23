import type { StreamingState } from "../hooks/useAskStream";

/** Honest progress copy (IR-329) -- one deterministic pipeline stage per
 *  line, never phrasing that reads as parallel agents (ADR-028). */
export function statusLineText(state: StreamingState): string | null {
  switch (state.stage) {
    case "searching":
      return "Searching the repository…";
    case "found": {
      if (!state.foundInfo) return null;
      const { passageCount, recordCount } = state.foundInfo;
      const passages = passageCount === 1 ? "passage" : "passages";
      const papers = recordCount === 1 ? "paper" : "papers";
      return `Found ${passageCount} ${passages} from ${recordCount} ${papers}`;
    }
    case "thinking":
      return "Thinking…";
    case "answering":
      // The answer itself is rendering now -- a status line above it would
      // be a stale caption competing with the thing it announced.
      return null;
  }
}

export function StreamStatusLine({ state }: { state: StreamingState }) {
  const text = statusLineText(state);
  if (!text) return null;

  return (
    <p aria-live="polite" className="flex items-center gap-2 text-[12px] font-medium text-stone-500">
      <span
        aria-hidden
        className="w-1.5 h-1.5 rounded-full bg-brand animate-pulse motion-reduce:animate-none"
      />
      {text}
    </p>
  );
}
