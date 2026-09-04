import type { RecordClearance } from "@/types/records";
import { cn } from "@/lib/utils";

const STATUS_DOT: Record<RecordClearance["status"], string> = {
  pending: "bg-amber-400",
  cleared: "bg-emerald-500",
  declined: "bg-amber-600",
  rejected: "bg-red-500",
};

/**
 * Compact per-office status row for a workspace case card — the parallel-
 * review equivalent of a card-sized status line. Deliberately not the full
 * `ClearanceTrack` (built for the paper view's roomy right rail): a list of
 * many cards needs one line per case, not a vertical track repeated N times.
 * Shares only the underlying data shape (`RecordClearance`), not the component.
 */
export function WorkspaceOfficePills({ clearances }: { clearances: RecordClearance[] }) {
  if (clearances.length === 0) return null;

  return (
    <div className="flex flex-wrap items-center gap-1.5">
      {clearances.map((c) => (
        <span
          key={c.office}
          className="inline-flex items-center gap-1.5 px-2 py-1 rounded-md bg-stone-50 border border-stone-200 text-[11px] font-semibold text-stone-700"
        >
          <span className={cn("w-1.5 h-1.5 rounded-full", STATUS_DOT[c.status])} aria-hidden />
          {c.office_label}
        </span>
      ))}
    </div>
  );
}
