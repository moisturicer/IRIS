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
 * tagged: a version is never worked out from a timestamp.
 *
 * Review comments (IR-419) are entries too, each tagged with the version it
 * was made against. A reply is not an entry of its own: it sits under the
 * comment it answers, as on a pull request, and threads are one level deep.
 */
import { formatDate, joinLabels } from "@/lib/utils";
import type { RecordTracker, ReviewComment, TrackerResubmission } from "@/types/records";

export type TimelineKind =
  | "routing"
  | "review"
  | "revision"
  | "revision_resolved"
  | "document_request"
  | "version"
  | "reassignment"
  | "extension"
  | "comment";

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
  /** A comment entry's own: the comment, and its replies, oldest first. */
  comment?: { root: ReviewComment; replies: ReviewComment[] };
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
  // party answered. A withdrawal closes them too, unanswered, and says so:
  // the record was withdrawn, or the party that asked took its request back
  // (IR-272).
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

  // A coordinator moved a seat (IR-623). The names are null to a viewer who
  // may not read the review, and the act still says what happened.
  for (const r of tracker.reassignments ?? []) {
    entries.push({
      key: `reassignment-${r.seat}`,
      kind: "reassignment",
      at: r.at,
      actor: r.by_name,
      party: r.label,
      act: r.from_name && r.to_name ? `Reassigned from ${r.from_name} to ${r.to_name}` : "Reassigned a reviewer",
      status: null,
      note: r.reason || null,
      details: [],
      version: null,
    });
  }

  // A due date moved (ADR-043 §6): by a coordinator, with their reason, or by
  // IRIS for a document-request pause, whose wording is a fact, not a note.
  for (const h of tracker.assignment_deadline_history ?? []) {
    for (const e of h.extensions) {
      entries.push({
        key: `extension-${e.id}`,
        kind: "extension",
        at: e.created_at,
        actor: e.system ? null : e.actor_name,
        party: h.label,
        act: e.system ? "Due date moved for a document request" : "Extended the due date",
        status: null,
        note: e.system ? null : e.reason || null,
        details: [`Due ${formatDate(e.due_at)}, was ${formatDate(e.previous_due_at)}`],
        version: null,
      });
    }
  }

  // Null as `reviews` is, to a viewer who may not read the review (IR-479).
  const comments = tracker.review_comments ?? [];
  const roots = new Set(comments.filter((c) => c.reply_to === null).map((c) => c.id));
  const replies = new Map<number, ReviewComment[]>();
  for (const c of comments) {
    if (c.reply_to !== null && roots.has(c.reply_to)) {
      replies.set(c.reply_to, [...(replies.get(c.reply_to) ?? []), c]);
    }
  }
  for (const c of comments) {
    // A reply whose comment is not here stands alone, rather than be lost.
    if (c.reply_to !== null && roots.has(c.reply_to)) continue;
    entries.push({
      key: `comment-${c.id}`,
      kind: "comment",
      at: c.created_at,
      actor: c.author_name,
      party: null,
      act: c.reply_to === null ? "Commented" : "Replied",
      status: null,
      note: c.body,
      details: [],
      version: c.version,
      // Replies keep the server's order, which is oldest first.
      comment: { root: c, replies: replies.get(c.id) ?? [] },
    });
  }

  // Oldest first. An entry with no time sorts before every dated one; ties
  // keep the order above, which is the tracker's own. `sort` is stable.
  const time = (e: TimelineEntry) => (e.at ? Date.parse(e.at) : Number.NEGATIVE_INFINITY);
  // Compared, not subtracted: two undated entries would give -∞ - -∞ = NaN.
  return entries.sort((a, b) => (time(a) < time(b) ? -1 : time(a) > time(b) ? 1 : 0));
}
