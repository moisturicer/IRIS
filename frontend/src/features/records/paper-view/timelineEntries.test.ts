/**
 * The Review section's timeline, built from the tracker alone (IR-412; spec
 * §4.7). One ordered list, oldest first, of who did what, as which party,
 * when -- every name and label the server's.
 */
import { describe, expect, it } from "vitest";

import type {
  DocumentRequest, RecordTracker, ReviewComment, TrackerResubmission, TrackerReview,
} from "@/types/records";

import { timelineEntries } from "./timelineEntries";

function tracker(overrides: Partial<RecordTracker> = {}): RecordTracker {
  return {
    record_id: 7,
    record_type: "Thesis / Research",
    workflow_state: "in_review",
    workflow_state_label: "In review",
    current_holders: [],
    parties: [],
    routing_history: [],
    routing_recorded_from: null,
    reviews: [],
    versions: [],
    review_comments: [],
    resubmissions: [],
    document_requests: [],
    clearances: [],
    resubmission: { count: 0, last_resubmitted_at: null, declining_office: null, offices_preserved: [] },
    ...overrides,
  };
}

const review = (overrides: Partial<TrackerReview>): TrackerReview => ({
  id: 1,
  party: "itso",
  label: "ITSO",
  status: "approved",
  status_label: "Approved",
  comment: "",
  reviewed_by_name: "Mara Santos",
  created_at: "2026-09-05T08:00:00Z",
  version: null,
  ...overrides,
});

const comment = (overrides: Partial<ReviewComment>): ReviewComment => ({
  id: 1,
  author: 3,
  author_name: "Rhea Owner",
  body: "Is the consent form attached?",
  version: 1,
  reply_to: null,
  created_at: "2026-09-07T08:00:00Z",
  edited_at: null,
  can_edit: false,
  ...overrides,
});

const resubmission = (overrides: Partial<TrackerResubmission>): TrackerResubmission => ({
  id: 1,
  party: "ierc",
  label: "IERC",
  state: "open",
  state_label: "Open",
  reason: "Consent form is missing.",
  review: 2,
  version: null,
  requested_by: "Leo Tan",
  created_at: "2026-09-06T08:00:00Z",
  resolved_at: null,
  resolved_by: null,
  ...overrides,
});

const documentRequest = (overrides: Partial<DocumentRequest>): DocumentRequest => ({
  id: 1,
  party: "ierc",
  label: "IERC",
  state: "open",
  state_label: "Open",
  message: "Please attach the signed consent forms.",
  requested_by: "Leo Tan",
  created_at: "2026-09-04T08:00:00Z",
  closed_at: null,
  can_manage: false,
  items: [
    {
      id: 11, slot: 3, label: "Ethics Clearance", state: "missing", state_label: "Missing",
      upload: null, uploaded_at: null, rejection_reason: null, decided_at: null,
    },
  ],
  ...overrides,
});

describe("timelineEntries", () => {
  it("lists routing, reviews, revisions and document requests oldest first", () => {
    const entries = timelineEntries(
      tracker({
        routing_history: [
          {
            group_id: "g2", from: "adviser", from_label: "Adviser", to: ["itso", "ierc"],
            to_labels: ["ITSO", "IERC"], actor: "Dr. Reyes", reason: "Has a patentable claim.",
            at: "2026-09-03T08:00:00Z",
          },
          {
            group_id: "g1", from: null, from_label: null, to: ["adviser"], to_labels: ["Adviser"],
            actor: "Rhea Owner", reason: "", at: "2026-09-01T08:00:00Z",
          },
        ],
        reviews: [review({ id: 1, created_at: "2026-09-05T08:00:00Z" })],
        document_requests: [documentRequest({})],
      }),
    );

    expect(entries.map((e) => e.act)).toEqual([
      "Submitted to Adviser",
      "Routed to ITSO + IERC",
      "Asked for documents",
      "Approved",
    ]);
  });

  it("names the actor and the party each acted as, in the server's words", () => {
    const [routed, reviewed] = timelineEntries(
      tracker({
        routing_history: [
          {
            group_id: "g", from: "adviser", from_label: "Adviser", to: ["itso"], to_labels: ["ITSO"],
            actor: "Dr. Reyes", reason: "Has a patentable claim.", at: "2026-09-03T08:00:00Z",
          },
        ],
        reviews: [review({ comment: "Cleared for disclosure." })],
      }),
    );

    expect(routed).toMatchObject({ actor: "Dr. Reyes", party: "Adviser", note: "Has a patentable claim." });
    expect(reviewed).toMatchObject({
      actor: "Mara Santos",
      party: "ITSO",
      act: "Approved",
      note: "Cleared for disclosure.",
    });
  });

  it("shows a request for changes once, as the review that made it, with where it stands", () => {
    const entries = timelineEntries(
      tracker({
        reviews: [
          review({
            id: 2, party: "ierc", label: "IERC", status: "declined",
            status_label: "Resubmission requested", comment: "Consent form is missing.",
            reviewed_by_name: "Leo Tan", created_at: "2026-09-06T08:00:00Z",
          }),
        ],
        resubmissions: [resubmission({ review: 2 })],
      }),
    );

    expect(entries).toHaveLength(1);
    expect(entries[0]).toMatchObject({
      actor: "Leo Tan",
      party: "IERC",
      act: "Resubmission requested",
      status: "Open",
      note: "Consent form is missing.",
    });
  });

  it("adds the resolution when the owner resubmits, once for every request it answered", () => {
    const resolvedAt = "2026-09-10T08:00:00Z";
    const entries = timelineEntries(
      tracker({
        reviews: [
          review({ id: 2, party: "ierc", label: "IERC", status: "declined", status_label: "Resubmission requested" }),
          review({ id: 3, party: "ktto", label: "KTTO", status: "declined", status_label: "Resubmission requested" }),
        ],
        resubmissions: [
          resubmission({
            id: 1, review: 2, state: "resubmitted", state_label: "Resubmitted",
            resolved_at: resolvedAt, resolved_by: "Rhea Owner",
          }),
          resubmission({
            id: 2, review: 3, party: "ktto", label: "KTTO", state: "resubmitted",
            state_label: "Resubmitted", resolved_at: resolvedAt, resolved_by: "Rhea Owner",
          }),
        ],
      }),
    );

    const last = entries[entries.length - 1];
    // The owner is not a party, so the entry names no party.
    expect(last).toMatchObject({ act: "Resubmitted", at: resolvedAt, actor: "Rhea Owner", party: null });
    expect(last.details).toEqual(["Answers the requests for changes from IERC and KTTO"]);
    expect(entries.filter((e) => e.act === "Resubmitted")).toHaveLength(1);
  });

  it("says a withdrawn request was closed unanswered, not answered", () => {
    const entries = timelineEntries(
      tracker({
        reviews: [review({ id: 2, party: "ierc", label: "IERC", status: "declined", status_label: "Resubmission requested" })],
        resubmissions: [
          resubmission({
            review: 2, state: "withdrawn", state_label: "Withdrawn",
            resolved_at: "2026-09-10T08:00:00Z", resolved_by: "Rhea Owner",
          }),
        ],
      }),
    );

    const last = entries[entries.length - 1];
    expect(last).toMatchObject({ act: "Withdrawn", actor: "Rhea Owner" });
    expect(last.details).toEqual(["Closes the request for changes from IERC, unanswered"]);
  });

  it("keeps a request for changes whose review it cannot find, rather than lose it", () => {
    const [entry] = timelineEntries(tracker({ resubmissions: [resubmission({ review: 99 })] }));

    expect(entry).toMatchObject({ act: "Asked for changes", actor: "Leo Tan", party: "IERC", status: "Open" });
  });

  it("lists what a document request asked for, and why an upload was turned down", () => {
    const [entry] = timelineEntries(
      tracker({
        document_requests: [
          documentRequest({
            items: [
              {
                id: 11, slot: 3, label: "Ethics Clearance", state: "missing", state_label: "Missing",
                upload: null, uploaded_at: null, rejection_reason: "Unsigned.", decided_at: null,
              },
            ],
          }),
        ],
      }),
    );

    expect(entry).toMatchObject({ actor: "Leo Tan", party: "IERC", status: "Open" });
    expect(entry.details).toEqual(["Ethics Clearance · Missing", "Turned down an upload of Ethics Clearance: “Unsigned.”"]);
  });

  it("leaves document requests out when the viewer may not read them", () => {
    expect(timelineEntries(tracker({ document_requests: null }))).toEqual([]);
  });

  it("shows a retired party's historical entries under the server's label, word for word", () => {
    const [entry] = timelineEntries(
      tracker({
        routing_history: [
          {
            group_id: "g", from: "intake", from_label: "Intake (retired)", to: ["itso"],
            to_labels: ["ITSO"], actor: "RDCO Staff", reason: "", at: "2026-08-01T08:00:00Z",
          },
        ],
      }),
    );

    expect(entry.party).toBe("Intake (retired)");
  });

  it("puts entries with no recorded time first, in the order the tracker gave them", () => {
    const entries = timelineEntries(
      tracker({
        reviews: [
          review({ id: 1, status_label: "Approved", created_at: "2026-09-05T08:00:00Z" }),
          review({ id: 2, status_label: "Negative finding", created_at: null }),
        ],
      }),
    );

    expect(entries.map((e) => e.act)).toEqual(["Negative finding", "Approved"]);
  });

  it("makes each version an entry, and tags each review with the version it was made against", () => {
    const entries = timelineEntries(
      tracker({
        versions: [
          {
            number: 1, cause: "submission", cause_label: "Submission",
            created_at: "2026-09-01T08:00:00Z", created_by_name: "Rhea Owner",
            manuscript_url: "/api/v1/records/7/versions/1/manuscript/",
          },
          {
            number: 2, cause: "revision", cause_label: "Revision",
            created_at: "2026-09-07T08:00:00Z", created_by_name: "Rhea Owner", manuscript_url: null,
          },
        ],
        reviews: [
          review({ id: 1, status_label: "Approved", created_at: "2026-09-05T08:00:00Z", version: 1 }),
          review({ id: 2, status_label: "Approved", created_at: "2026-09-08T08:00:00Z", version: 2 }),
        ],
      }),
    );

    expect(entries.map((e) => [e.act, e.version])).toEqual([
      ["v1 submitted", null],
      ["Approved", 1],
      ["v2 submitted", null],
      ["Approved", 2],
    ]);
    expect(entries[0].actor).toBe("Rhea Owner");
    expect(entries[0].party).toBeNull();
    expect(entries[2].details).toEqual(["Revision · no manuscript"]);
  });

  it("shows a coordinator's reassignment with who moved it and why (IR-623)", () => {
    const entries = timelineEntries(
      tracker({
        reassignments: [{
          seat: 9, party: "itso", label: "ITSO", from_name: "Maria Reyes", to_name: "Juan Santos",
          by_name: "Cora Dinator", reason: "Maria is on leave.", at: "2026-09-06T08:00:00Z",
        }],
      }),
    );

    expect(entries).toHaveLength(1);
    expect(entries[0]).toMatchObject({
      kind: "reassignment",
      act: "Reassigned from Maria Reyes to Juan Santos",
      actor: "Cora Dinator",
      party: "ITSO",
      note: "Maria is on leave.",
      at: "2026-09-06T08:00:00Z",
    });
  });

  it("shows each due-date extension, by hand or by a document pause, in time order", () => {
    const entries = timelineEntries(
      tracker({
        reviews: [review({ created_at: "2026-09-09T08:00:00Z" })],
        assignment_deadline_history: [{
          assignment: 3, party: "itso", label: "ITSO",
          extensions: [
            {
              id: 1, previous_due_at: "2026-09-10T15:59:00Z", due_at: "2026-09-14T15:59:00Z",
              reason: "Committee meets Monday.", system: false, actor: 4, actor_name: "Cora Dinator",
              created_at: "2026-09-08T08:00:00Z",
            },
            {
              id: 2, previous_due_at: "2026-09-14T15:59:00Z", due_at: "2026-09-16T15:59:00Z",
              reason: "Document request pause: 2 working days.", system: true, actor: null,
              actor_name: null, created_at: "2026-09-10T08:00:00Z",
            },
          ],
        }],
      }),
    );

    expect(entries.map((e) => [e.kind, e.act, e.actor, e.party])).toEqual([
      ["extension", "Extended the due date", "Cora Dinator", "ITSO"],
      ["review", "Approved", "Mara Santos", "ITSO"],
      ["extension", "Due date moved for a document request", null, "ITSO"],
    ]);
    expect(entries[0].note).toBe("Committee meets Monday.");
    expect(entries[0].details).toHaveLength(1);
    expect(entries[0].details[0]).toMatch(/^Due .+, was .+$/);
    // The system's own wording is a fact, not something anyone wrote.
    expect(entries[2].note).toBeNull();
  });

  it("tags no review written before versions, rather than invent v1", () => {
    const entries = timelineEntries(tracker({ reviews: [review({ version: null })], versions: null }));

    expect(entries.map((e) => e.version)).toEqual([null]);
  });

  it("adds each comment where it was made, by its author, tagged with its version", () => {
    const entries = timelineEntries(tracker({
      reviews: [review({ created_at: "2026-09-05T08:00:00Z" })],
      review_comments: [
        comment({ id: 1, created_at: "2026-09-04T08:00:00Z", body: "Before the review." }),
        comment({ id: 2, created_at: "2026-09-06T08:00:00Z", body: "After it.", version: 2 }),
      ],
    }));

    expect(entries.map((e) => e.key)).toEqual(["comment-1", "review-1", "comment-2"]);
    const [first, , second] = entries;
    expect(first).toMatchObject({
      kind: "comment", actor: "Rhea Owner", party: null, act: "Commented",
      note: "Before the review.", version: 1,
    });
    expect(second.version).toBe(2);
  });

  it("threads each reply under the comment it answers, oldest first", () => {
    const entries = timelineEntries(tracker({
      review_comments: [
        comment({ id: 1, body: "Which sample size?" }),
        comment({ id: 2, reply_to: 1, body: "Forty.", created_at: "2026-09-08T08:00:00Z" }),
        comment({ id: 3, body: "Another question.", created_at: "2026-09-08T09:00:00Z" }),
        comment({ id: 4, reply_to: 1, body: "Why forty?", created_at: "2026-09-09T08:00:00Z" }),
      ],
    }));

    expect(entries.map((e) => e.key)).toEqual(["comment-1", "comment-3"]);
    expect(entries[0].comment?.replies.map((r) => r.body)).toEqual(["Forty.", "Why forty?"]);
    expect(entries[1].comment?.replies).toEqual([]);
  });

  it("tags no comment on a record with no version, rather than invent v1", () => {
    const [entry] = timelineEntries(tracker({ review_comments: [comment({ version: null })] }));

    expect(entry.version).toBeNull();
  });

  it("leaves comments out when the viewer may not read the review", () => {
    expect(timelineEntries(tracker({ review_comments: null }))).toEqual([]);
  });
});
