import { useId, useState } from "react";
import type { ReaderUsage } from "@/api/runtimeReader";
import { cn } from "@/lib/utils";

/** "11K", "9.6K", "256K", "1.2M". */
export function shortTokens(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(n >= 10_000_000 ? 0 : 1)}M`;
  if (n >= 10_000) return `${Math.round(n / 1_000)}K`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(1).replace(/\.0$/, "")}K`;
  return String(n);
}

const SEGMENTS = 12;
const SPAN = 360 / SEGMENTS;
const GAP = 7;

const point = (r: number, degrees: number, centre: number) => {
  const a = ((degrees - 90) * Math.PI) / 180;
  return `${(centre + r * Math.cos(a)).toFixed(2)} ${(centre + r * Math.sin(a)).toFixed(2)}`;
};
/** An arc of the ring from one angle to another, clockwise from twelve o'clock. */
const arc = (r: number, from: number, to: number, centre: number) =>
  `M ${point(r, from, centre)} A ${r} ${r} 0 0 1 ${point(r, to, centre)}`;

/**
 * Twelve beads set round a bezel like a watch face, filled clockwise from the
 * top as the conversation fills the context. Beads held for the answer are striped.
 */
function Ring({ used, reserved = 0, size, stroke }: { used: number; reserved?: number; size: number; stroke: number }) {
  const centre = size / 2;
  const r = centre - stroke / 2 - 0.5;
  const held = reserved > 0 ? Math.max(1, Math.round(reserved * SEGMENTS)) : 0;
  return (
    <svg aria-hidden width={size} height={size} viewBox={`0 0 ${size} ${size}`} className="shrink-0">
      {Array.from({ length: SEGMENTS }, (_, i) => {
        const from = i * SPAN + GAP / 2;
        const to = (i + 1) * SPAN - GAP / 2;
        const fill = Math.max(0, Math.min(1, used * SEGMENTS - i));
        const reservedBead = SEGMENTS - i <= held;
        return <g key={i} fill="none" strokeLinecap="round" strokeWidth={stroke}>
          <path d={arc(r, from, to, centre)} className={reservedBead ? "stroke-brand/30" : "stroke-stone-300"}
            strokeDasharray={reservedBead ? "2 2" : undefined} />
          {fill > 0 && <path d={arc(r, from, from + (to - from) * fill, centre)} className="stroke-brand" />}
        </g>;
      })}
    </svg>
  );
}

/**
 * How much of the model's context the conversation now holds, as the provider
 * reported it for the latest step. It grows turn by turn and drops back once
 * older context is condensed. A ring beside Send; the reading on hover or focus.
 */
export function TokenUsageMeter({ usage }: { usage: ReaderUsage }) {
  const [hovered, setHovered] = useState(false);
  const [pinned, setPinned] = useState(false);
  const open = hovered || pinned;
  const tipId = useId();
  const capacity = usage.capacity_tokens ?? 0;
  if (!capacity) return null;
  const used = usage.context_tokens;
  const share = Math.min(1, used / capacity);
  const reserved = Math.min(1 - share, (usage.reserved_tokens ?? 0) / capacity);
  const percent = Math.round(share * 100);
  return (
    <span className="relative inline-flex" onMouseEnter={() => setHovered(true)} onMouseLeave={() => setHovered(false)}>
      <button type="button" aria-describedby={open ? tipId : undefined} aria-label={`Context window ${percent}% used`}
        onFocus={() => setHovered(true)} onBlur={() => { setHovered(false); setPinned(false); }}
        onClick={() => setPinned(v => !v)} onKeyDown={e => { if (e.key === "Escape") { setPinned(false); setHovered(false); } }}
        className="inline-flex size-8 items-center justify-center rounded-full transition-colors hover:bg-stone-100">
        <Ring used={share} size={20} stroke={3} />
      </button>
      {open && <span id={tipId} role="tooltip"
        className={cn("absolute bottom-full right-0 z-30 mb-2 flex w-60 items-center gap-3.5 rounded-xl border border-stone-200 bg-white p-3.5 text-left shadow-card-md",
          "motion-safe:animate-fade-in-up")}>
        <span className="relative inline-flex shrink-0">
          <Ring used={share} reserved={reserved} size={52} stroke={5} />
          <span className="absolute inset-0 flex items-center justify-center font-display text-[15px] tabular-nums text-stone-900">{percent}%</span>
        </span>
        <span className="min-w-0">
          <span className="block font-display text-[15px] leading-tight text-stone-900">Context window</span>
          <span className="mt-1 block text-[13px] tabular-nums text-stone-600">
            <strong className="font-semibold text-stone-800">{shortTokens(used)}</strong> / {shortTokens(capacity)} tokens
          </span>
          {reserved > 0 && <span className="mt-1 flex items-center gap-1.5 text-[12px] text-stone-600">
            <svg aria-hidden width="14" height="6" className="shrink-0"><line x1="1" y1="3" x2="13" y2="3"
              className="stroke-brand/30" strokeWidth="4" strokeLinecap="round" strokeDasharray="2 2" /></svg>
            Reserved for response
          </span>}
        </span>
      </span>}
    </span>
  );
}
