import type { Ref } from "react";

import { FOCUS_RING } from "@/components/ui/interaction";
import { AskIrisMark } from "@/features/ai/components/AskIrisIcons";
import { cn } from "@/lib/utils";

/**
 * The reader's private Notes, closed (IR-580): a smaller round icon just above
 * Ask IRIS, in the same corner, so the two tools that share the reading
 * workspace's one panel sit together.
 */
export function NotesFab({ onOpen, buttonRef }: { onOpen: () => void; buttonRef?: Ref<HTMLButtonElement> }) {
  return (
    <button
      ref={buttonRef}
      type="button"
      onClick={onOpen}
      aria-label="Notes"
      title="Your private notes on this paper"
      className={cn(
        "fixed z-30 bottom-24 right-6 reading-split:right-9 w-11 h-11 rounded-full flex items-center justify-center",
        "bg-white border border-stone-300 text-brand shadow-card-md",
        "hover:bg-stone-100 hover:-translate-y-0.5 motion-reduce:hover:translate-y-0 transition-all duration-200",
        FOCUS_RING,
      )}
    >
      <i className="fas fa-note-sticky" aria-hidden />
    </button>
  );
}

/**
 * Ask IRIS, closed (IR-569): one round icon at the bottom right, over every
 * section that has the assistant. Its tooltip is its name; the panel it opens
 * says what it is.
 */
export function AskIrisFab({ onOpen, buttonRef }: { onOpen: () => void; buttonRef?: Ref<HTMLButtonElement> }) {
  return (
    <button
      ref={buttonRef}
      type="button"
      onClick={onOpen}
      aria-label="Ask IRIS"
      title="Ask IRIS about this paper"
      className={cn(
        "fixed z-30 bottom-5 right-5 reading-split:right-8 w-14 h-14 rounded-full flex items-center justify-center",
        "bg-brand text-white shadow-card-md",
        "hover:bg-brand-light hover:-translate-y-0.5 motion-reduce:hover:translate-y-0 transition-all duration-200",
        FOCUS_RING,
      )}
    >
      <AskIrisMark className="w-7 h-7" />
    </button>
  );
}
