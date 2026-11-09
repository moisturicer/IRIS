import { useId, useState } from "react";
import type { ReaderUsage } from "@/api/runtimeReader";
import { cn } from "@/lib/utils";

/** "11K", "256K", "1.2M". */
export function shortTokens(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(n >= 10_000_000 ? 0 : 1)}M`;
  if (n >= 1_000) return `${Math.round(n / 1_000)}K`;
  return String(n);
}

const SEGMENTS = 12;

/** A row of ticks, filled by share: the conversation's working memory at a glance. */
function Ticks({ used, reserved, className }: { used: number; reserved: number; className?: string }) {
  const filled = used > 0 ? Math.max(1, Math.round(used * SEGMENTS)) : 0;
  const held = Math.round(reserved * SEGMENTS);
  return (
    <span aria-hidden className={cn("flex items-end gap-[2px]", className)}>
      {Array.from({ length: SEGMENTS }, (_, i) => {
        const fromEnd = SEGMENTS - i;
        return <span key={i} className={cn("w-[3px] rounded-[1px] transition-colors duration-300",
          i < filled ? "h-3 bg-brand" : fromEnd <= held ? "h-2 bg-brand/30" : "h-2 bg-stone-300")} />;
      })}
    </span>
  );
}

/**
 * How much of the model's context the latest step used, as the provider
 * reported it. A tick gauge in the composer; the reading on hover or focus.
 */
export function TokenUsageMeter({ usage }: { usage: ReaderUsage }) {
  const [hovered, setHovered] = useState(false);
  const [pinned, setPinned] = useState(false);
  const open = hovered || pinned;
  const tipId = useId();
  const capacity = usage.capacity_tokens ?? 0;
  if (!capacity) return null;
  const used = usage.context_tokens;
  const reserved = usage.reserved_tokens ?? 0;
  const share = Math.min(1, used / capacity);
  const percent = Math.round(share * 100);
  return (
    <span className="relative inline-flex" onMouseEnter={() => setHovered(true)} onMouseLeave={() => setHovered(false)}>
      <button type="button" aria-describedby={open ? tipId : undefined} aria-label={`Working memory ${percent}% used`}
        onFocus={() => setHovered(true)} onBlur={() => { setHovered(false); setPinned(false); }}
        onClick={() => setPinned(v => !v)} onKeyDown={e => { if (e.key === "Escape") { setPinned(false); setHovered(false); } }}
        className="inline-flex h-8 items-center gap-1.5 rounded-full px-2.5 text-[12px] font-medium tabular-nums text-stone-500 hover:bg-stone-100 focus-visible:outline-brand">
        <Ticks used={share} reserved={0} />
        {percent}%
      </button>
      {open && <span id={tipId} role="tooltip"
        className="absolute bottom-full left-0 z-30 mb-2 w-60 rounded-lg border-l-[3px] border-brand bg-white px-3 py-2.5 text-left shadow-card-md motion-safe:animate-fade-in-up">
        <span className="block font-display text-[15px] text-stone-900">Working memory</span>
        <Ticks used={share} reserved={Math.min(1 - share, reserved / capacity)} className="mt-2" />
        <span className="mt-2 block text-[12px] leading-snug text-stone-600">
          The last step read <strong className="font-semibold text-stone-800">{shortTokens(used)}</strong> of{" "}
          {shortTokens(capacity)} tokens{reserved > 0 && <>, with {shortTokens(reserved)} kept free for the answer</>}.
        </span>
      </span>}
    </span>
  );
}
