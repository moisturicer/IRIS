/**
 * What a requested document is called, everywhere (IR-411; spec §4.10).
 *
 * One vocabulary for the owner's banner, the Files section and the reviewer's
 * list, so "Requested" means one thing wherever a document request appears:
 *
 * | Stored item state                     | Shown as                       |
 * |---------------------------------------|--------------------------------|
 * | `missing`                             | Requested                      |
 * | `uploaded`                            | Uploaded · awaiting review     |
 * | `accepted`                            | Accepted                       |
 * | `rejected`, or `missing` with a reason | Replacement needed            |
 *
 * A rejected upload puts its item back to `missing` with the reviewer's reason
 * (ADR-022 §3.4), so the reason is what tells "asked again" from "asked".
 */
import { TONES } from "@/components/ui/statusTones";
import type { DocumentRequestItem } from "@/types/records";

export type ItemStatus = "requested" | "awaiting_review" | "accepted" | "replacement_needed";

export function itemStatus(item: Pick<DocumentRequestItem, "state" | "rejection_reason">): ItemStatus {
  switch (item.state) {
    case "uploaded":
      return "awaiting_review";
    case "accepted":
      return "accepted";
    case "rejected":
      return "replacement_needed";
    case "missing":
      return item.rejection_reason ? "replacement_needed" : "requested";
  }
}

export const ITEM_STATUS_WORDS: Record<ItemStatus, string> = {
  requested:          "Requested",
  awaiting_review:    "Uploaded · awaiting review",
  accepted:           "Accepted",
  replacement_needed: "Replacement needed",
};

/** By meaning (IR-358): waiting on the owner is attention, with a reviewer is active. */
export const ITEM_STATUS_TONES: Record<ItemStatus, string> = {
  requested:          TONES.active,
  awaiting_review:    TONES.quiet,
  accepted:           TONES.settled,
  replacement_needed: TONES.attention,
};

/** The chip for one item: its word, in its tone. */
export function ItemStatusChip({ item }: { item: Pick<DocumentRequestItem, "state" | "rejection_reason"> }) {
  const status = itemStatus(item);
  return (
    <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-2xs font-semibold ${ITEM_STATUS_TONES[status]}`}>
      {ITEM_STATUS_WORDS[status]}
    </span>
  );
}
