import { useId, useState } from "react";
import type { ReaderUsage } from "@/api/runtimeReader";

/** "11K", "256K", "1.2M". */
export function shortTokens(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(n >= 10_000_000 ? 0 : 1)}M`;
  if (n >= 1_000) return `${Math.round(n / 1_000)}K`;
  return String(n);
}

const RING = 2 * Math.PI * 8;

/**
 * The context window of the latest model call, as the provider reported it,
 * with the conversation's token totals. A ring in the composer; the breakdown on hover or focus.
 */
export function TokenUsageMeter({ usage, totals }: {
  /** The latest run's usage: its last call is how full the window is now. */
  usage: ReaderUsage;
  /** Every run in the conversation, summed. */
  totals: { input_tokens: number; output_tokens: number; cost_usd: number; calls: number };
}) {
  const [hovered, setHovered] = useState(false);
  const [pinned, setPinned] = useState(false);
  const open = hovered || pinned;
  const setOpen = setHovered;
  const tipId = useId();
  const capacity = usage.capacity_tokens ?? 0;
  const used = usage.context_tokens;
  const reserved = usage.reserved_tokens ?? 0;
  const share = capacity ? Math.min(1, used / capacity) : 0;
  const reservedShare = capacity ? Math.min(1 - share, reserved / capacity) : 0;
  const percent = Math.round(share * 100);
  return (
    <span className="relative inline-flex" onMouseEnter={() => setOpen(true)} onMouseLeave={() => setOpen(false)}>
      <button type="button" aria-describedby={open ? tipId : undefined} onFocus={() => setOpen(true)} onBlur={() => setOpen(false)}
        onClick={() => setPinned(v => !v)} onKeyDown={e => { if (e.key === "Escape") { setPinned(false); setHovered(false); } }}
        aria-label={capacity ? `Context window ${percent}% used` : "Token usage"}
        className="inline-flex h-8 w-8 items-center justify-center rounded-full text-stone-500 hover:bg-stone-100 focus-visible:outline-brand">
        <svg viewBox="0 0 20 20" className="h-5 w-5 -rotate-90" aria-hidden>
          <circle cx="10" cy="10" r="8" fill="none" strokeWidth="2.5" className="stroke-stone-200" />
          <circle cx="10" cy="10" r="8" fill="none" strokeWidth="2.5" strokeLinecap="round" className="stroke-brand"
            strokeDasharray={`${share * RING} ${RING}`} />
        </svg>
      </button>
      {open && <span id={tipId} role="tooltip"
        className="absolute bottom-full left-0 z-30 mb-2 w-64 rounded-xl border border-stone-200 bg-white p-3 text-left text-[13px] text-stone-700 shadow-card-md">
        <span className="block font-semibold text-stone-500">Context window</span>
        {capacity > 0 && <>
          <span className="mt-1 flex items-baseline justify-between">
            <span className="text-stone-900">{shortTokens(used)} / {shortTokens(capacity)} tokens</span>
            <span className="tabular-nums">{percent}%</span>
          </span>
          <span className="mt-2 flex h-2 w-full overflow-hidden rounded-full bg-stone-100" aria-hidden>
            <span className="h-full rounded-l-full bg-brand" style={{ width: `${share * 100}%` }} />
            <span className="flex-1" />
            {reservedShare > 0 && <span className="h-full bg-[repeating-linear-gradient(135deg,theme(colors.brand.DEFAULT)_0_3px,transparent_3px_6px)]"
              style={{ width: `${reservedShare * 100}%` }} />}
          </span>
          {reserved > 0 && <span className="mt-1.5 flex items-center gap-1.5 text-stone-500">
            <span aria-hidden className="inline-block h-2 w-3 rounded-sm bg-[repeating-linear-gradient(135deg,theme(colors.brand.DEFAULT)_0_2px,transparent_2px_4px)]" />
            Reserved for response ({shortTokens(reserved)})
          </span>}
        </>}
        <span className="mt-3 block border-t border-stone-200 pt-2 font-semibold text-stone-500">This conversation</span>
        <span className="mt-1 grid grid-cols-2 gap-y-0.5 tabular-nums">
          <span>Input</span><span className="text-right text-stone-900">{totals.input_tokens.toLocaleString()}</span>
          <span>Output</span><span className="text-right text-stone-900">{totals.output_tokens.toLocaleString()}</span>
          <span>Model calls</span><span className="text-right text-stone-900">{totals.calls}</span>
          <span>Cost</span><span className="text-right text-stone-900">${totals.cost_usd.toFixed(4)}</span>
        </span>
      </span>}
    </span>
  );
}
