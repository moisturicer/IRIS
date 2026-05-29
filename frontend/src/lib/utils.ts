import { clsx, type ClassValue } from "clsx";
import { format, parseISO, isValid } from "date-fns";
import type { PipelineStatus } from "./constants";

export function cn(...inputs: ClassValue[]) {
  return clsx(inputs);
}

export function formatDate(value: string | Date | null | undefined, pattern = "MMM d, yyyy"): string {
  if (!value) return "—";
  const date = typeof value === "string" ? parseISO(value) : value;
  return isValid(date) ? format(date, pattern) : "—";
}

const PIPELINE_LABELS: Record<PipelineStatus, string> = {
  draft:           "Draft",
  adviser_review:  "Adviser Review",
  approved:        "Approved — Ongoing",
  completed:       "Completed",
  rdco_intake:     "RDCO Intake Review",
  itso_review:     "ITSO Review",
  parallel_review: "Parallel Office Review",
  rdco_review:     "RDCO Final Review",
  published:       "Published",
  declined:        "Revision Requested",
  rejected:        "Rejected",
  pending_delete:  "Pending Deletion",
};

export function pipelineLabel(status: PipelineStatus | string): string {
  return PIPELINE_LABELS[status as PipelineStatus] ?? status;
}

export function downloadBlob(data: Blob, filename: string) {
  const url = URL.createObjectURL(data);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  anchor.click();
  URL.revokeObjectURL(url);
}

/** Parse filename from Content-Disposition (attachment; filename="…"). */
export function filenameFromDisposition(header: string | undefined | null): string | null {
  if (!header) return null;
  const star = /filename\*=UTF-8''([^;]+)/i.exec(header);
  if (star) return decodeURIComponent(star[1].trim());
  const plain = /filename="?([^";\n]+)"?/i.exec(header);
  return plain ? plain[1].trim() : null;
}
