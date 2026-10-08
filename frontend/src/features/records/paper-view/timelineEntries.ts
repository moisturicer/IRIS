/**
 * The Review section's timeline (IR-412; spec §4.7): one ordered list of what
 * has happened in a record's review, oldest first.
 *
 * Built from the tracker payload alone (`GET /records/<id>/tracker/`), which
 * already carries every kind of entry: routing, reviews and findings, requests
 * for changes and their resolution, and document requests. Nothing is derived
 * from a role or a stage here. Every name and label -- the actor, the party,
 * a review's verdict, a request's state -- is the server's, word for word, so
 * a retired party such as Intake reads however the server words it.
 *
 * Each version is an entry of its own ("v2 submitted"), and each review is
 * tagged with the version it was made against (IR-416). Nothing else is
 * tagged: a version is never worked out from a timestamp. Review comments
 * join when their backend lands (IR-419).
 */
import type { RecordTracker, TrackerResubmission } from "@/types/records";

export type TimelineKind =
  | "routing"
  | "review"
  | "revision"
  | "revision_resolved"
  | "document_request"
  | "version";

export interface TimelineEntry {
  key: string;
  kind: TimelineKind;
  /** When it happened. Null where the server has no time for it. */
  at: string | null;
  /** Who did it, as the server names them. */
  actor: string | null;
  /** The party they acted as, in the server's words. */
  party: string | null;
  /** What was done. */
  act: string;
  /** Where an open request stands now, in the server's words. */
  status: string | null;
  /** What they wrote, verbatim. Plain text; never render as markup. */
  note: string | null;
  /** Further lines: the items asked for, an upload turned down. */
  details: string[];
  /**
   * The version a review was made against (IR-416). Null for every other
   * kind of entry, and for a review written before versions existed: no tag
   * is shown rather than an invented "v1" (spec §4.11).
   */
  version: number | null;
}

/** "IERC", "IERC and KTTO", "ITSO, IERC and KTTO". */
function joinLabels(labels: string[]): string {
  if (labels.length <= 1) return labels.join("");
  return `${labels.slice(0, -1).join(", ")} and ${labels[labels.length - 1]}`;
}

export function timelineEntries(tracker: RecordTracker): TimelineEntry[] {
  const entries: TimelineEntry[] = [];

  for (const g of tracker.routing_history) {
    const to = g.to_labels.join(" + ");
    entries.push({
      key: `routing-${g.group_id}`,
      kind: "routing",
      at: g.at,
      actor: g.actor,
      party: g.from_label,
      act: g.from_label ? `Routed to ${to}` : `Submitted to ${to}`,
      status: null,
      note: g.reason || null,
      details: [],
      version: null,
    });
  }

  // A request for changes is recorded twice: as the `declined` review that
  // carries its comment, and as the request that tracks it. It is one act,
  // so it is shown once, as the review, with the request's state beside it.
  const requestByReview = new Map<number, TrackerResubmission>(
    tracker.resubmissions.map((r) => [r.review, r]),
  );
  // Null to a viewer who may not read the review (IR-479). The timeline is
  // drawn for participants only, who always get them; listing none is the
  // honest reading for anyone else, never an invented empty history.
  const reviews = tracker.reviews ?? [];
  const reviewIds = new Set(reviews.map((r) => r.id));

  for (const r of reviews) {
    const request = requestByReview.get(r.id);
    entries.push({
      key: `review-${r.id}`,
      kind: "review",
      at: r.created_at,
      actor: r.reviewed_by_name,
      party: r.label,
      act: r.status_label,
      status: request?.state_label ?? null,
      note: r.comment || null,
      details: [],
      version: r.version ?? null,
    });
  }

  for (const r of tracker.resubmissions) {
    if (reviewIds.has(r.review)) continue;
    entries.push({
      key: `revision-${r.id}`,
      kind: "revision",
      at: r.created_at,
      actor: r.requested_by,
      party: r.label,
      act: "Asked for changes",
      status: r.state_label,
      note: r.reason || null,
      details: [],
      version: null,
    });
  }

  // One resubmission answers every open request at once, so the requests it
  // closed share a time, a state and who closed them: one entry, naming every
  // party answered. A withdrawal (the record was withdrawn) closes them too,
  // unanswered, and says so.
  const resolutions = new Map<string, TrackerResubmission[]>();
  for (const r of tracker.resubmissions) {
    if (r.state === "open" || !r.resolved_at) continue;
    const key = `${r.resolved_at}|${r.state}|${r.resolved_by ?? ""}`;
    resolutions.set(key, [...(resolutions.get(key) ?? []), r]);
  }
  for (const [key, closed] of resolutions) {
    const [first] = closed;
    const requests = closed.length === 1 ? "the request" : "the requests";
    const from = joinLabels(closed.map((r) => r.label));
    entries.push({
      key: `resolved-${key}`,
      kind: "revision_resolved",
      at: first.resolved_at,
      // The owner, who is not a party: no party is named.
      actor: first.resolved_by,
      party: null,
      act: first.state_label,
      status: null,
      note: null,
      details: [
        first.state === "resubmitted"
          ? `Answers ${requests} for changes from ${from}`
          : `Closes ${requests} for changes from ${from}, unanswered`,
      ],
      version: null,
    });
  }

  // Null when the viewer may not read them (IR-349): nothing to show.
  for (const d of tracker.document_requests ?? []) {
    entries.push({
      key: `documents-${d.id}`,
      kind: "document_request",
      at: d.created_at,
      actor: d.requested_by,
      party: d.label,
      act: "Asked for documents",
      status: d.state_label,
      note: d.message || null,
      details: [
        ...d.items.map((i) => `${i.label} · ${i.state_label}`),
        ...d.items
          .filter((i) => i.rejection_reason)
          .map((i) => `Turned down an upload of ${i.label}: “${i.rejection_reason}”`),
      ],
      version: null,
    });
  }

  // Null as `reviews` is, to a viewer who may not read the review (IR-479).
  // The owner who submitted is not a party: no party is named.
  for (const v of tracker.versions ?? []) {
    entries.push({
      key: `version-${v.number}`,
      kind: "version",
      at: v.created_at,
      actor: v.created_by_name,
      party: null,
      act: `v${v.number} submitted`,
      status: null,
      note: null,
      details: [v.manuscript_url ? v.cause_label : `${v.cause_label} · no manuscript`],
      version: null,
    });
  }

  // Oldest first. An entry with no time sorts before every dated one; ties
  // keep the order above, which is the tracker's own. `sort` is stable.
  const time = (e: TimelineEntry) => (e.at ? Date.parse(e.at) : Number.NEGATIVE_INFINITY);
  // Compared, not subtracted: two undated entries would give -∞ - -∞ = NaN.
  return entries.sort((a, b) => (time(a) < time(b) ? -1 : time(a) > time(b) ? 1 : 0));
}
