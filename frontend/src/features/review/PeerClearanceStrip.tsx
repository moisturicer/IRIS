import type { PeerClearance } from "@/types/reviews";
import { cn } from "@/lib/utils";

/**
 * What the *other* offices have decided.
 *
 * This is the row's reason to exist. Under parallel review a reviewer is
 * recording one office's clearance, not approving the record, and the useful
 * question before opening anything is "am I the last one?". A strip showing
 * ITSO cleared and KTTO pending answers it at a glance.
 *
 * Status only, never the peer's comment: seeing *that* a peer decided is
 * orientation, reading *why* before forming your own view is influence, and the
 * comparison the evaluation runs depends on those staying independent.
 *
 * Icon *and* label, never colour alone -- these sit at 10-11px where hue is the
 * least reliable thing about them.
 */

const PEER_META: Record<
  PeerClearance["status"],
  { icon: string; className: string }
> = {
  cleared:  { icon: "fa-check",             className: "bg-emerald-50 text-emerald-700 border-emerald-200" },
  pending:  { icon: "fa-hourglass-half",    className: "bg-stone-50 text-stone-500 border-stone-200" },
  declined: { icon: "fa-arrow-rotate-left", className: "bg-amber-50 text-amber-700 border-amber-200" },
  rejected: { icon: "fa-xmark",             className: "bg-red-50 text-red-700 border-red-200" },
};

export function PeerClearanceStrip({ peers }: { peers: PeerClearance[] }) {
  if (peers.length === 0) {
    // A sequential stage (Adviser, RDCO) has no peers by definition. Saying so
    // beats an empty gap the reader has to interpret.
    return <span className="text-[11px] text-stone-400">No parallel offices</span>;
  }

  return (
    <ul className="flex flex-wrap items-center gap-1.5">
      {peers.map((p) => {
        const meta = PEER_META[p.status];
        return (
          <li key={p.office}>
            <span
              className={cn(
                "inline-flex items-center gap-1 rounded border px-1.5 py-0.5 text-[10px] font-semibold",
                meta.className,
              )}
              title={`${p.office_label}: ${p.status_label}`}
            >
              <i className={cn("fas", meta.icon, "text-[8px]")} aria-hidden />
              {p.office_label}
              <span className="sr-only"> — {p.status_label}</span>
            </span>
          </li>
        );
      })}
    </ul>
  );
}
