import { forwardRef, type KeyboardEvent } from "react";
import { Button } from "@/components/ui";

/** Where find is, as the bar reports it. */
export type FindStatus =
  | { kind: "idle" }
  | { kind: "searching" }
  | { kind: "none" }
  | { kind: "found"; current: number; total: number; searching: boolean }
  | { kind: "no-text" };

export interface PaperFindProps {
  query: string;
  status: FindStatus;
  onQueryChange: (query: string) => void;
  onNext: () => void;
  onPrevious: () => void;
  onClose: () => void;
}

function statusText(status: FindStatus): string {
  switch (status.kind) {
    case "idle":
      return "";
    case "searching":
      return "Searching…";
    case "none":
      return "No matches";
    case "no-text":
      return "This paper has no searchable text";
    case "found":
      return `${status.current} of ${status.total}${status.searching ? "…" : ""}`;
  }
}

/**
 * Find in this paper (IR-353): a search of the open PDF's own text, in the
 * reader's toolbar. Not the header's search, which looks across records;
 * this one's label, placeholder and place in the reader all say "this
 * paper".
 *
 * Keyboard as in a browser's find: Enter for the next match, Shift+Enter
 * for the previous, Esc to close. The ref is the textbox, which the reader
 * focuses when find opens.
 */
export const PaperFind = forwardRef<HTMLInputElement, PaperFindProps>(function PaperFind(
  { query, status, onQueryChange, onNext, onPrevious, onClose },
  inputRef,
) {
  const found = status.kind === "found";
  const noText = status.kind === "no-text";

  const handleKeyDown = (event: KeyboardEvent<HTMLInputElement>) => {
    if (event.key === "Enter") {
      event.preventDefault();
      if (!found) return;
      if (event.shiftKey) onPrevious();
      else onNext();
    } else if (event.key === "Escape") {
      event.preventDefault();
      onClose();
    }
  };

  return (
    <div
      role="search"
      aria-label="Find in this paper"
      className="flex flex-wrap basis-full items-center gap-x-1 gap-y-0.5 pt-1"
    >
      <div className="relative flex-1 min-w-0">
        <i
          className="fas fa-magnifying-glass pointer-events-none absolute left-2.5 top-1/2 -translate-y-1/2 text-2xs text-stone-400"
          aria-hidden
        />
        <input
          ref={inputRef}
          type="search"
          value={query}
          onChange={(event) => onQueryChange(event.target.value)}
          onKeyDown={handleKeyDown}
          aria-label="Find in this paper"
          placeholder="Find in this paper"
          autoComplete="off"
          spellCheck={false}
          className="w-full h-11 lg:h-8 rounded-lg border border-stone-200 bg-white pl-7 pr-2 text-sm text-stone-800 placeholder:text-stone-400 focus:border-brand/60 focus:outline-none focus-visible:ring-2 focus-visible:ring-brand/30 [&::-webkit-search-cancel-button]:hidden"
        />
      </div>
      {/* "This paper has no searchable text" takes a line of its own under
          the textbox, and there is nothing to step through: beside it, at
          360px, it squeezed the textbox to 38px. */}
      <span
        role="status"
        className={
          noText
            ? "order-last basis-full pb-0.5 pl-1 text-2xs font-semibold text-stone-500"
            : "shrink-0 min-w-[3.5rem] text-right text-2xs font-semibold text-stone-500 tabular-nums"
        }
      >
        {statusText(status)}
      </span>
      {!noText && (
        <>
          <Button variant="ghost" size="icon" onClick={onPrevious} disabled={!found} aria-label="Previous match">
            <i className="fas fa-chevron-up" aria-hidden />
          </Button>
          <Button variant="ghost" size="icon" onClick={onNext} disabled={!found} aria-label="Next match">
            <i className="fas fa-chevron-down" aria-hidden />
          </Button>
        </>
      )}
      <Button variant="ghost" size="icon" onClick={onClose} aria-label="Close find">
        <i className="fas fa-xmark" aria-hidden />
      </Button>
    </div>
  );
});
