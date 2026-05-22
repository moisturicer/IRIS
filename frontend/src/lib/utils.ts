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
  draft:          "Draft",
  adviser_review: "Adviser Review",
  ktto_review:    "KTTO / TBI Review",
  rdco_review:    "RDCO Review",
  published:      "Published",
  declined:       "Declined",
  pending_delete: "Pending Deletion",
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
