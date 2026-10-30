/**
 * Where each kind of open request is answered on Paper View (IR-625). The
 * wording is the server's (`submitter_status`); only the place is the
 * client's, because only the client knows its own page.
 */
import type { WaitingItem } from "@/types/records";

/** The Overview's element that answers each kind, as a fragment id. */
export const WAITING_TARGET: Record<WaitingItem["kind"], string> = {
  revision: "revision-requested",
  document: "documents-requested",
};

export const waitingHref = (recordId: number, item: Pick<WaitingItem, "kind">) =>
  `/records/${recordId}?section=overview#${WAITING_TARGET[item.kind]}`;
