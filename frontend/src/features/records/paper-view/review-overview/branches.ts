/**
 * The review drawn as branches: the Adviser, the offices side by side, then
 * RDCO. The offices review at the same time, so nothing puts one before
 * another. Every word is the server's (`tracker`, `revision.open`, document
 * requests); this only decides which row a party stands in and its tone.
 */
import type { DocumentRequest, OpenRevisionRequest, RecordTracker, TrackerPartyRow } from "@/types/records";

import { RETIRED_PARTY } from "../ReviewRoutingTracker";

/** `asking` waits on the owner; `done` and `busy` are the clearance strip's green and amber. */
export type BranchTone = "asking" | "done" | "busy" | "refused" | "idle";

export interface BranchAsk {
  key: string;
  kind: "revision" | "document";
  /** "Asked for changes · on v1", "Asked for 2 documents". */
  act: string;
  /** The reviewer's own words. Plain text. */
  words: string | null;
}

export interface BranchNode {
  party: string;
  label: string;
  /** The server's words for where the party is. */
  status: string;
  tone: BranchTone;
  /** Kept from an earlier version: the clearance survived a resubmission. */
  kept: string | null;
  asks: BranchAsk[];
}

const OUTCOME_GOOD: ReadonlySet<string> = new Set(["cleared", "approved"]);
const OUTCOME_BAD: ReadonlySet<string> = new Set(["not_cleared", "negative_finding", "rejected", "declined"]);

function statusOf(row: TrackerPartyRow): { status: string; tone: BranchTone } {
  const asked = [row.changes_requested ? "Changes requested" : null, row.awaiting_document ? "Awaiting document" : null].filter(Boolean);
  if (asked.length > 0) return { status: asked.join(" · "), tone: "asking" };
  // "Pending" is not a conclusion (IR-272).
  const outcome = row.outcome && row.outcome !== "pending" ? row.outcome : null;
  const status = [
    row.state === "completed" && row.outcome_label && outcome ? null : row.state_label,
    outcome ? row.outcome_label : null,
    row.in_pool ? "Unassigned" : null,
    row.withdrawn_by_decision ?? null,
  ].filter(Boolean).join(" · ");
  const tone: BranchTone =
    outcome && OUTCOME_BAD.has(outcome) ? "refused"
      : row.state === "active" ? (row.in_pool ? "idle" : "busy")
        : row.state === "completed" || (outcome && OUTCOME_GOOD.has(outcome)) ? "done"
          : "idle";
  return { status, tone };
}

function askOf(request: DocumentRequest): BranchAsk {
  const n = request.items.length;
  return {
    key: `document-${request.id}`,
    kind: "document",
    act: n === 1 ? "Asked for a document" : `Asked for ${n} documents`,
    words: request.message || null,
  };
}

/** What each party is asking the owner for now, its revision request first. */
export function asksByParty(
  revisions: readonly OpenRevisionRequest[], documents: readonly DocumentRequest[],
): Map<string, { label: string; asks: BranchAsk[] }> {
  const found = new Map<string, { label: string; asks: BranchAsk[] }>();
  const add = (party: string, label: string, ask: BranchAsk) => {
    const entry = found.get(party) ?? { label, asks: [] };
    entry.asks.push(ask);
    found.set(party, entry);
  };
  revisions.forEach((r) => add(r.party, r.label, {
    key: `revision-${r.id}`,
    kind: "revision",
    act: r.version != null ? `Asked for changes · on v${r.version}` : "Asked for changes",
    words: r.reason,
  }));
  documents.filter((r) => r.state === "open").forEach((r) => add(r.party, r.label, askOf(r)));
  return found;
}

/**
 * The rows, top to bottom: one party, the offices, one party. A party that
 * asks is drawn even where the tracker does not list it (it is still loading,
 * or its read failed), so the owner is never left without the request itself.
 */
export function branchRows(
  tracker: RecordTracker | null,
  revisions: readonly OpenRevisionRequest[],
  documents: readonly DocumentRequest[],
): BranchNode[][] {
  const asks = asksByParty(revisions, documents);
  const nodes: BranchNode[] = (tracker?.parties ?? [])
    .filter((p) => p.party !== (RETIRED_PARTY as string) && (p.state !== "not_required" || asks.has(p.party)))
    .map((p) => {
      const mine = asks.get(p.party)?.asks ?? [];
      const { status, tone } = statusOf(p);
      return {
        party: p.party,
        label: p.label,
        status,
        tone: mine.length > 0 ? "asking" : tone,
        // An office that asks again now says that instead.
        kept: p.preserved && mine.length === 0 && tone === "done" ? p.carryover_label ?? "Preserved" : null,
        asks: mine,
      };
    });
  const listed = new Set(nodes.map((n) => n.party));
  asks.forEach(({ label, asks: mine }, party) => {
    if (!listed.has(party)) nodes.push({ party, label, status: "", tone: "asking", kept: null, asks: mine });
  });
  const at = (test: (party: string) => boolean) => nodes.filter((n) => test(n.party));
  return [
    at((p) => p === "adviser"),
    at((p) => p !== "adviser" && p !== "rdco"),
    at((p) => p === "rdco"),
  ].filter((row) => row.length > 0);
}
