import { cn, pipelineLabel } from "@/lib/utils";
import type { PipelineStatus } from "@/lib/constants";

const colors: Record<string, string> = {
  draft:           "bg-gray-100 text-gray-600",
  adviser_review:  "bg-yellow-100 text-yellow-700",
  approved:        "bg-teal-100 text-teal-700",      // proposal approved — ongoing
  completed:       "bg-emerald-100 text-emerald-700", // proposal research finished
  rdco_intake:     "bg-orange-100 text-orange-700",
  itso_review:     "bg-indigo-100 text-indigo-700",
  ktto_review:     "bg-blue-100 text-blue-700",
  parallel_review: "bg-blue-100 text-blue-700",
  rdco_review:     "bg-purple-100 text-purple-700",
  published:       "bg-green-100 text-green-700",
  declined:        "bg-amber-100 text-amber-700",    // revision requested
  rejected:        "bg-red-100 text-red-700",         // terminal rejection
  pending_delete:  "bg-rose-100 text-rose-700",
};

export function StatusBadge({ status }: { status: PipelineStatus }) {
  return (
    <span className={cn("inline-block px-2 py-0.5 rounded-full text-[11px] font-semibold", colors[status] ?? "bg-gray-100 text-gray-600")}>
      {pipelineLabel(status)}
    </span>
  );
}
