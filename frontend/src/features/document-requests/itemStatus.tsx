/**
 * What a requested document is called, everywhere (IR-411; spec §4.10).
 *
 * One vocabulary for the owner's banner, the Files section and the reviewer's
 * list, so "Requested" means one thing wherever a document request appears:
 *
 * | Stored item state                      | Shown as           |
 * |----------------------------------------|--------------------|
 * | `missing`                              | Requested          |
 * | `uploaded`, or `accepted` before IR-1338 | Supplied         |
 * | `rejected`, or `missing` with a reason | Replacement needed |
 *
 * Nothing is accepted or rejected any more (ADR-022 Amendment 10, IR-1338): a
 * sent document is supplied. "Replacement needed" is kept for items a reviewer
 * rejected before then, which went back to `missing` with the reason.
 */
import { TONES } from "@/components/ui/statusTones";
import type { DocumentRequestItem } from "@/types/records";

export type ItemStatus = "requested" | "supplied" | "replacement_needed";

export function itemStatus(item: Pick<DocumentRequestItem, "state" | "rejection_reason">): ItemStatus {
  switch (item.state) {
    case "uploaded":
    case "accepted":
      return "supplied";
    case "rejected":
      return "replacement_needed";
    case "missing":
      return item.rejection_reason ? "replacement_needed" : "requested";
  }
}

export const ITEM_STATUS_WORDS: Record<ItemStatus, string> = {
  requested:          "Requested",
  supplied:           "Supplied",
  replacement_needed: "Replacement needed",
};

/**
 * By meaning (IR-358; 01-design-system §0). Requested is with the owner, so
 * active; a supplied document is settled; one asked for again is attention,
 * because the owner must act.
 */
export const ITEM_STATUS_TONES: Record<ItemStatus, string> = {
  requested:          TONES.active,
  supplied:           TONES.settled,
  replacement_needed: TONES.attention,
};

/** The chip for one item: its word, in its tone. */
export function ItemStatusChip({ item }: { item: Pick<DocumentRequestItem, "state" | "rejection_reason"> }) {
  const status = itemStatus(item);
  return (
    <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-label font-semibold ${ITEM_STATUS_TONES[status]}`}>
      {ITEM_STATUS_WORDS[status]}
    </span>
  );
}
