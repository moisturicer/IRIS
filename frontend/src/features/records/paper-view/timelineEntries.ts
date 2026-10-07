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
 * Versions and review comments join this list when their backend lands
 * (IR-416, IR-419); each entry then carries a version tag.
 */
import type { RecordTracker, TrackerResubmission } from "@/types/records";

export type TimelineKind =
  | "routing"
  | "review"
  | "revision"
  | "revision_resolved"
  | "document_request";

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
    });
  }

  // A request for changes is recorded twice: as the `declined` review that
  // carries its comment, and as the request that tracks it. It is one act,
  // so it is shown once, as the review, with the request's state beside it.
  const requestByReview = new Map<number, TrackerResubmission>(
    tracker.resubmissions.map((r) => [r.review, r]),
  );
  const reviewIds = new Set(tracker.reviews.map((r) => r.id));

  for (const r of tracker.reviews) {
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
    });
  }

  // One resubmission answers every open request at once, so the requests it
  // closed share a time and a state: one entry, naming every party answered.
  const resolutions = new Map<string, TrackerResubmission[]>();
  for (const r of tracker.resubmissions) {
    if (r.state === "open" || !r.resolved_at) continue;
    const key = `${r.resolved_at}|${r.state}`;
    resolutions.set(key, [...(resolutions.get(key) ?? []), r]);
  }
  for (const [key, closed] of resolutions) {
    const labels = closed.map((r) => r.label);
    entries.push({
      key: `resolved-${key}`,
      kind: "revision_resolved",
      at: closed[0].resolved_at,
      actor: null,
      party: null,
      act: closed[0].state_label,
      status: null,
      note: null,
      details: [
        labels.length === 1
          ? `Answers the request for changes from ${labels[0]}`
          : `Answers the requests for changes from ${joinLabels(labels)}`,
      ],
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
    });
  }

  // Oldest first. An entry with no time sorts before every dated one; ties
  // keep the order above, which is the tracker's own. `sort` is stable.
  const time = (e: TimelineEntry) => (e.at ? Date.parse(e.at) : Number.NEGATIVE_INFINITY);
  // Compared, not subtracted: two undated entries would give -∞ - -∞ = NaN.
  return entries.sort((a, b) => (time(a) < time(b) ? -1 : time(a) > time(b) ? 1 : 0));
}
