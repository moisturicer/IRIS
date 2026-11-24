/**
 * Where each kind of open request is answered on Paper View (IR-625). The
 * wording is the server's (`submitter_status`); only the place is the
 * client's, because only the client knows its own page.
 */
import type { WaitingItem } from "@/types/records";

/** The Overview's element that explains each kind, as a fragment id. */
export const WAITING_TARGET: Record<WaitingItem["kind"], string> = {
  revision: "revision-requested",
  document: "documents-requested",
};

/**
 * Both kinds are answered in Review's Documents tab (IR-1318): a document by
 * uploading it, a revision by uploading changes and *Submit new version*.
 * `kind` stays in the signature so a later kind can land elsewhere.
 */
export const waitingHref = (recordId: number, _item: Pick<WaitingItem, "kind">) =>
  `/records/${recordId}?section=review&documents=open`;
