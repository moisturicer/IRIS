import type { RecordClearance } from "@/types/records";
import { formatDate } from "@/lib/utils";
import { cn } from "@/lib/utils";

interface ClearanceTrackProps {
  clearances: RecordClearance[];
}

/**
 * Presentation only. The *wording* comes from the server as `status_label`
 * (IR-139) so an institution can rename a status without a frontend release;
 * what stays here is the icon and colour, which are this design system's
 * business and not the server's.
 */
const STATUS_META: Record<
  RecordClearance["status"],
  { icon: string; dot: string; text: string }
> = {
  cleared:  { icon: "fa-check",             dot: "bg-emerald-500", text: "text-emerald-700" },
  pending:  { icon: "fa-hourglass-half",    dot: "bg-stone-300",   text: "text-stone-500" },
  declined: { icon: "fa-arrow-rotate-left", dot: "bg-amber-500",   text: "text-amber-700" },
  rejected: { icon: "fa-xmark",             dot: "bg-red-500",     text: "text-red-700" },
};

/**
 * Per-office clearance state.
 *
 * This is the screen's reason to exist: when one office requests revisions, the
 * others keep their clearance. A clearance decided *before* the current
 * submission is a preserved one, and is labelled as such — otherwise the
 * contribution is invisible and the record just looks partly reviewed.
 */
export function ClearanceTrack({ clearances }: ClearanceTrackProps) {
  if (clearances.length === 0) {
    return (
      <section className="bg-white border border-stone-200 rounded-2xl p-5">
        <h2 className="text-[11px] font-bold uppercase tracking-wider text-stone-400 mb-2">
          Office Clearance
        </h2>
        <p className="text-[12px] text-stone-500">
          No office clearances yet. They are created when RDCO accepts the record at intake.
        </p>
      </section>
    );
  }

  const cleared = clearances.filter((c) => c.status === "cleared").length;

  return (
    <section className="bg-white border border-stone-200 rounded-2xl p-5">
      <div className="flex items-center justify-between gap-3 mb-3">
        <h2 className="text-[11px] font-bold uppercase tracking-wider text-stone-400">
          Office Clearance
        </h2>
        <span className="text-[11px] font-bold text-stone-500">
          {cleared} of {clearances.length} cleared
        </span>
      </div>

      <ul className="space-y-2.5">
        {clearances.map((c) => {
          const meta = STATUS_META[c.status];
          // Server-supplied (IR-139). This was derived here from the most
          // recent decline, which dated preservation to the reviewer's
          // decision rather than the owner's resubmission -- a different rule
          // from the one `resubmit_record` actually applies.
          const preserved = c.preserved;

          return (
            <li key={c.office} className="flex items-start gap-3">
              <span className={cn("w-2 h-2 rounded-full mt-1.5 shrink-0", meta.dot)} />
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-2 flex-wrap">
                  <span className="text-[13px] font-bold text-stone-900">{c.office_label}</span>
                  <span className={cn("text-[11px] font-semibold flex items-center gap-1", meta.text)}>
                    <i className={cn("fas", meta.icon, "text-[9px]")} aria-hidden />
                    {c.status_label}
                  </span>
                  {preserved && (
                    <span
                      className="px-1.5 py-0.5 rounded bg-emerald-50 text-emerald-700 border border-emerald-200 text-[10px] font-bold flex items-center gap-1"
                      title="Cleared before the current submission and carried over — this office will not review again"
                    >
                      <i className="fas fa-shield-halved text-[8px]" aria-hidden />
                      Preserved
                    </span>
                  )}
                  <span className="ml-auto text-[11px] text-stone-400 shrink-0">
                    {formatDate(c.updated_at, "MMM d")}
                  </span>
                </div>
                {c.comment && (
                  <p className="text-[12px] text-stone-600 mt-1 leading-relaxed">“{c.comment}”</p>
                )}
                {c.reviewed_by_name && (
                  <p className="text-[11px] text-stone-400 mt-0.5">— {c.reviewed_by_name}</p>
                )}
              </div>
            </li>
          );
        })}
      </ul>
    </section>
  );
}
