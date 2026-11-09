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
 * IRIS's working-memory ring: twelve beads set round a bezel like a watch face,
 * filled clockwise from the top as the conversation takes up the model's
 * context. The beads at the end the answer is kept free for are drawn lighter.
 */
function Ring({ used, reserved, size, stroke }: { used: number; reserved: number; size: number; stroke: number }) {
  const centre = size / 2;
  const r = centre - stroke / 2 - 0.5;
  const held = Math.round(reserved * SEGMENTS);
  return (
    <svg aria-hidden width={size} height={size} viewBox={`0 0 ${size} ${size}`} className="shrink-0">
      {Array.from({ length: SEGMENTS }, (_, i) => {
        const from = i * SPAN + GAP / 2;
        const to = (i + 1) * SPAN - GAP / 2;
        const fill = Math.max(0, Math.min(1, used * SEGMENTS - i));
        const reservedBead = SEGMENTS - i <= held;
        return <g key={i} fill="none" strokeLinecap="round" strokeWidth={stroke}>
          <path d={arc(r, from, to, centre)}
            className={reservedBead ? "stroke-brand/25" : "stroke-stone-300"} />
          {fill > 0 && <path d={arc(r, from, from + (to - from) * fill, centre)}
            className="stroke-brand" />}
        </g>;
      })}
    </svg>
  );
}

/**
 * How much of the model's context the latest step used, as the provider
 * reported it. A ring in the composer; the reading on hover or focus.
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
        className="inline-flex size-8 items-center justify-center rounded-full transition-colors hover:bg-stone-100">
        <Ring used={share} reserved={0} size={20} stroke={3} />
      </button>
      {open && <span id={tipId} role="tooltip"
        className={cn("absolute bottom-full left-0 z-30 mb-2 flex w-64 items-center gap-3.5 rounded-xl border border-stone-200 bg-white p-3.5 text-left shadow-card-md",
          "motion-safe:animate-fade-in-up")}>
        <span className="relative inline-flex shrink-0">
          <Ring used={share} reserved={Math.min(1 - share, reserved / capacity)} size={52} stroke={5} />
          <span className="absolute inset-0 flex items-center justify-center font-display text-[15px] tabular-nums text-stone-900">{percent}%</span>
        </span>
        <span className="min-w-0">
          <span className="block font-display text-[15px] leading-tight text-stone-900">Working memory</span>
          <span className="mt-1 block text-[12px] leading-snug text-stone-600">
            The last step read <strong className="font-semibold text-stone-800">{shortTokens(used)}</strong> of{" "}
            {shortTokens(capacity)} tokens{reserved > 0 && <>, with {shortTokens(reserved)} kept free for the answer</>}.
          </span>
        </span>
      </span>}
    </span>
  );
}
