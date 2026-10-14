import type { Ref } from "react";

import { FOCUS_RING } from "@/components/ui/interaction";
import { AskIrisMark } from "@/features/ai/components/AskIrisIcons";
import { cn } from "@/lib/utils";

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
        "bg-brand text-white shadow-[0_6px_18px_rgb(107_15_18/0.35)]",
        "hover:bg-brand-light hover:-translate-y-0.5 motion-reduce:hover:translate-y-0 transition-all duration-200",
        FOCUS_RING,
      )}
    >
      <AskIrisMark className="w-7 h-7" />
    </button>
  );
}
