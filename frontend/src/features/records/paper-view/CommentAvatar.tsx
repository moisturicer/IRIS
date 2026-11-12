import { cn } from "@/lib/utils";

import { initials } from "./commentThreads";

/** Quiet tones from the palette, so two people are told apart without a rainbow. */
const TONES = [
  "bg-brand-100 text-brand",
  "bg-stone-200 text-stone-800",
  "bg-cream text-brand-800",
  "bg-brand-50 text-brand-700",
];

function toneFor(name: string): string {
  let hash = 0;
  for (const char of name) hash = (hash * 31 + char.charCodeAt(0)) >>> 0;
  return TONES[hash % TONES.length];
}

/** A person's initials in a circle. Decoration: the name is always written beside it. */
export function CommentAvatar({ name, size }: { name: string | null; size: "md" | "sm" }) {
  return (
    <span
      aria-hidden="true"
      className={cn(
        "flex shrink-0 select-none items-center justify-center rounded-full font-semibold",
        size === "md" ? "h-9 w-9 text-xs" : "h-7 w-7 text-3xs",
        name ? toneFor(name) : "bg-stone-200 text-stone-600",
      )}
    >
      {initials(name)}
    </span>
  );
}
