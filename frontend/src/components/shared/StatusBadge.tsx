import { cn, pipelineLabel } from "@/lib/utils";
import type { PipelineStatus } from "@/lib/constants";

const colors: Record<string, string> = {
  draft:          "bg-gray-100 text-gray-600",
  adviser_review: "bg-yellow-100 text-yellow-700",
  ktto_review:    "bg-blue-100 text-blue-700",
  rdco_review:    "bg-purple-100 text-purple-700",
  published:      "bg-green-100 text-green-700",
  declined:       "bg-red-100 text-red-700",
  pending_delete: "bg-orange-100 text-orange-700",
};

export function StatusBadge({ status }: { status: PipelineStatus }) {
  return (
    <span className={cn("inline-block px-2 py-0.5 rounded-full text-[11px] font-semibold", colors[status] ?? "bg-gray-100 text-gray-600")}>
      {pipelineLabel(status)}
    </span>
  );
}
