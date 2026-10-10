/**
 * The capabilities adapter, as a table (IR-411; spec §4.8, §5 Seam 1).
 *
 * Each row is a Record detail payload and a viewer, and the exact set of
 * capabilities and sections the adapter must answer. The expected sets are
 * written out by hand from the spec and ADR-032, not recomputed the way the
 * adapter computes them, so a wrong rule shows up as a wrong row.
 */
import { describe, expect, it } from "vitest";

import type { DecisionFlags, RecordDetail, ReviewerSeat, SeatState } from "@/types/records";

import {
  capabilitiesFor,
  seatToOpen,
  sectionsFor,
  type Capability,
  type PaperSection,
  type Viewer,
} from "./capabilities";

const OWNER = 40;
const ADVISER = 30;
const STRANGER = 99;

/** Record detail's `decision` for a viewer who may not decide (IR-270). */
const NO_DECISION: DecisionFlags = {
  party: null, outcomes: [], blocked: null, closes: null, token: null, author_hints: [],
};

/** A published Thesis no viewer below takes part in, unless a row says so. */
function record(overrides: Partial<RecordDetail> = {}): RecordDetail {
  return {
    id: 7,
    title: "Flood Prediction in the Mananga Catchment",
    abstract: "A study.",
    year_accomplished: 2026,
    year_completed: null,
    abstract_file: "https://iris.test/media/manuscripts/thesis.pdf",
    classification_name: null,
    classification: null,
    psced: null,
    record_type_name: "Thesis/Research",
    record_type: "Thesis/Research",
    pipeline_status: "published",
    is_ip: false,
    ip_type: "",
    for_commercialization: false,
    community_extension: false,
    access_count: 0,
    file_count: 1,
    created_at: "2026-09-01T08:00:00Z",
    authors: [],
    adviser: ADVISER,
    added_by: null,
    requires_ethics_review: false,
    requested_itso: false,
    requested_ierc: false,
    requested_ktto: false,
    owners: [{ id: 1, user: OWNER, email: "o@cit.edu", full_name: "O. Wner", is_primary: true }],
    is_deleted: false,
    reviews: [],
    clearances: [],
    resubmission: { count: 0, last_resubmitted_at: null, declining_office: null, offices_preserved: [] },
    stage_label: "Published",
    files: [],
    workflow_state: "published",
    workflow_state_label: "Published",
    current_holders: [],
    capabilities: ["cite"],
    can_request_document: [],
    my_seats: [],
    is_participant: false,
    routing: { accept_and_route: false, route_as: null },
    office_review: { party: null, label: null, blocked: null, assignment: null },
    revision: { party: null, label: null, blocked: null, withdrawable: null, decision_blocked: null, open: [], new_version: null },
    decision: NO_DECISION,
    versions: null,
    manuscript_unsubmitted: false,
    ...overrides,
  };
}

/** One of the viewer's own seats, as `my_seats` carries it (IR-415). */
function seat(state: SeatState, id = 1): ReviewerSeat {
  return {
    id,
    assignment: 11,
    record: 7,
    party: "itso",
    party_label: "ITSO",
    reviewer: 51,
    reviewer_name: "ITSO Reviewer",
    state,
    state_label: state,
    source: "claimed",
    assigned_by: 51,
    assigned_at: "2026-10-01T08:00:00Z",
    opened_at: state === "assigned" ? null : "2026-10-02T08:00:00Z",
    done_at: state === "done" ? "2026-10-03T08:00:00Z" : null,
  };
}

const owner: Viewer = { id: OWNER, role_name: "Student" };
const adviser: Viewer = { id: ADVISER, role_name: "Adviser" };
const stranger: Viewer = { id: STRANGER, role_name: "Student" };
const itsoStaff: Viewer = { id: 51, role_name: "ITSO" };

interface Row {
  name: string;
  record: RecordDetail;
  viewer: Viewer | null;
  capabilities: Capability[];
  sections: PaperSection[];
}

const ROWS: Row[] = [
  {
    name: "a reader of a published paper may cite it, and nothing else",
    record: record(),
    viewer: stranger,
    capabilities: ["cite"],
    sections: ["overview", "paper"],
  },
  {
    name: "a record with no manuscript has no Paper section",
    record: record({ abstract_file: null, files: [] }),
    viewer: stranger,
    capabilities: ["cite"],
    sections: ["overview"],
  },
  {
    name: "a supplementary file alone is still a paper to read",
    record: record({
      abstract_file: null,
      files: [{ id: 3, filename: "paper.pdf", url: null, size_bytes: 10, created_at: "2026-09-01T08:00:00Z", can_remove: false }],
    }),
    viewer: stranger,
    capabilities: ["cite"],
    sections: ["overview", "paper"],
  },
  {
    name: "nobody signed in is nobody's participant",
    record: record({ can_request_document: ["adviser"] }),
    viewer: null,
    capabilities: ["cite"],
    sections: ["overview", "paper"],
  },
  {
    name: "the owner of a draft may continue it and edit its details",
    record: record({ pipeline_status: "draft", workflow_state: "draft", workflow_state_label: "Draft" }),
    viewer: owner,
    capabilities: ["cite", "continue_draft", "edit_details"],
    sections: ["overview", "paper", "review", "files"],
  },
  {
    name: "someone who can read another person's draft may not edit it",
    record: record({ pipeline_status: "draft", workflow_state: "draft", workflow_state_label: "Draft" }),
    viewer: stranger,
    capabilities: ["cite"],
    sections: ["overview", "paper"],
  },
  {
    // IR-274: this asked it of a stored `declined`, the retired pipeline's
    // revision, where "Resubmit for review" needed no server offer. Every
    // revision is a new version now, offered by the server.
    name: "the owner asked for a revision is offered no new version the server did not offer",
    record: record({ pipeline_status: "in_review", workflow_state: "awaiting_resubmission" }),
    viewer: owner,
    capabilities: ["cite", "edit_details"],
    sections: ["overview", "paper", "review", "files"],
  },
  {
    name: "a rejected record offers its owner no author action (invariant 5)",
    record: record({ pipeline_status: "rejected", workflow_state: "rejected" }),
    viewer: owner,
    capabilities: ["cite"],
    sections: ["overview", "paper", "review", "files"],
  },
  {
    name: "a published record's details are not editable by its owner",
    record: record(),
    viewer: owner,
    capabilities: ["cite"],
    sections: ["overview", "paper", "review", "files"],
  },
  {
    name: "an office that may only ask for documents is a participant, without a decision, and may attach files",
    record: record({ pipeline_status: "in_review", workflow_state: "in_review", can_request_document: ["ierc"] }),
    viewer: { id: 52, role_name: "IERC" },
    capabilities: ["cite", "request_document", "attach_file"],
    sections: ["overview", "paper", "review", "files"],
  },
  {
    name: "an Adviser taking part may not attach files, which is an office's act",
    record: record({ pipeline_status: "in_review", workflow_state: "in_review", can_request_document: ["adviser"] }),
    viewer: adviser,
    capabilities: ["cite", "request_document"],
    sections: ["overview", "paper", "review", "files"],
  },
  {
    name: "a reviewer's role alone opens nothing the server did not grant",
    record: record({ pipeline_status: "in_review", workflow_state: "in_review" }),
    viewer: adviser,
    capabilities: ["cite"],
    sections: ["overview", "paper"],
  },
  {
    name: "office staff may tag the IP type of a published record (phase 1, role-derived)",
    record: record(),
    viewer: itsoStaff,
    capabilities: ["cite", "tag_ip"],
    sections: ["overview", "paper"],
  },
  {
    name: "office staff may not tag a record that is not published",
    record: record({ pipeline_status: "in_review", workflow_state: "in_review" }),
    viewer: itsoStaff,
    capabilities: ["cite"],
    sections: ["overview", "paper"],
  },
  {
    name: "an Adviser is not office staff, and tags nothing",
    record: record(),
    viewer: adviser,
    capabilities: ["cite"],
    sections: ["overview", "paper"],
  },
  {
    name: "a seat to work is a review to open",
    record: record({
      pipeline_status: "in_review",
      workflow_state: "in_review",
      my_seats: [seat("assigned")],
      is_participant: true,
    }),
    viewer: itsoStaff,
    capabilities: ["cite", "open_review"],
    sections: ["overview", "paper", "review", "files"],
  },
  {
    name: "a past seat holder keeps Review and Files, with nothing left to do (IR-411's gap, IR-415)",
    record: record({
      pipeline_status: "in_review",
      workflow_state: "in_review",
      my_seats: [seat("done")],
      is_participant: true,
    }),
    viewer: itsoStaff,
    capabilities: ["cite"],
    sections: ["overview", "paper", "review", "files"],
  },
  {
    name: "an office member who never held a seat here is not a participant",
    record: record({ pipeline_status: "in_review", workflow_state: "in_review", is_participant: false }),
    viewer: itsoStaff,
    capabilities: ["cite"],
    sections: ["overview", "paper"],
  },
  {
    name: "the record's Adviser, holding its review on the new model, may accept and route (IR-261)",
    record: record({
      pipeline_status: "in_review",
      workflow_state: "submitted",
      my_seats: [{ ...seat("assigned"), party: "adviser", party_label: "Adviser", source: "entry" }],
      is_participant: true,
      routing: { accept_and_route: true, route_as: null },
    }),
    viewer: adviser,
    capabilities: ["cite", "open_review", "accept_route"],
    sections: ["overview", "paper", "review", "files"],
  },
  {
    name: "an office seat holder may route onward (IR-261)",
    record: record({
      pipeline_status: "in_review",
      workflow_state: "in_review",
      my_seats: [seat("in_review")],
      is_participant: true,
      routing: { accept_and_route: false, route_as: "itso" },
    }),
    viewer: itsoStaff,
    capabilities: ["cite", "open_review", "route"],
    sections: ["overview", "paper", "review", "files"],
  },
  {
    name: "an office seat holder may clear, record a finding and add a colleague (IR-269)",
    record: record({
      pipeline_status: "in_review",
      workflow_state: "in_review",
      my_seats: [seat("in_review")],
      is_participant: true,
      routing: { accept_and_route: false, route_as: "itso" },
      office_review: { party: "itso", label: "ITSO", blocked: null, assignment: 11 },
    }),
    viewer: itsoStaff,
    capabilities: ["cite", "open_review", "route", "office_review", "add_reviewer"],
    sections: ["overview", "paper", "review", "files"],
  },
  {
    name: "a seat holder may ask for a revision (IR-272)",
    record: record({
      pipeline_status: "in_review",
      workflow_state: "in_review",
      my_seats: [seat("in_review")],
      is_participant: true,
      revision: { party: "itso", label: "ITSO", blocked: null, withdrawable: null, decision_blocked: null, open: [], new_version: null },
    }),
    viewer: itsoStaff,
    capabilities: ["cite", "open_review", "request_revision"],
    sections: ["overview", "paper", "review", "files"],
  },
  {
    name: "a party that has asked is offered the withdrawal, not a second request (IR-272)",
    record: record({
      pipeline_status: "in_review",
      workflow_state: "awaiting_resubmission",
      my_seats: [seat("in_review")],
      is_participant: true,
      revision: {
        party: "itso", label: "ITSO", blocked: null, withdrawable: 5,
        decision_blocked: "Waiting on the author: ITSO asked for a revision.",
        open: [],
        new_version: null,
      },
    }),
    viewer: itsoStaff,
    capabilities: ["cite", "open_review", "withdraw_revision"],
    sections: ["overview", "paper", "review", "files"],
  },
  {
    name: "the record's Adviser may accept & publish or reject, beside accept & route (IR-270)",
    record: record({
      pipeline_status: "in_review",
      workflow_state: "in_review",
      is_participant: true,
      routing: { accept_and_route: true, route_as: null },
      decision: { ...NO_DECISION, party: "adviser", outcomes: ["publish", "reject"], token: "t" },
    }),
    viewer: adviser,
    capabilities: ["cite", "accept_route", "accept_publish", "reject"],
    sections: ["overview", "paper", "review", "files"],
  },
  {
    name: "a Proposal's Adviser may accept or reject it (IR-271)",
    record: record({
      record_type_name: "Proposal",
      record_type: "Proposal",
      pipeline_status: "in_review",
      workflow_state: "in_review",
      is_participant: true,
      decision: { ...NO_DECISION, party: "adviser", outcomes: ["accept", "reject"], token: "t" },
    }),
    viewer: adviser,
    capabilities: ["cite", "accept_proposal", "reject"],
    sections: ["overview", "paper", "review", "files"],
  },
  {
    name: "RDCO's reviewer may also keep the record unlisted (IR-270)",
    record: record({
      pipeline_status: "in_review",
      workflow_state: "final_review",
      is_participant: true,
      decision: {
        ...NO_DECISION, party: "rdco", outcomes: ["publish", "keep_unlisted", "reject"], token: "t",
      },
    }),
    viewer: { id: 61, role_name: "RDCO" },
    capabilities: ["cite", "accept_publish", "keep_unlisted", "reject"],
    sections: ["overview", "paper", "review", "files"],
  },
  {
    name: "on the adviser-first model the owner is offered a new version when the server says so (IR-273)",
    record: record({
      pipeline_status: "in_review",
      workflow_state: "awaiting_resubmission",
      revision: {
        party: null, label: null, blocked: null, withdrawable: null,
        decision_blocked: "Waiting on the author: IERC asked for a revision.",
        open: [],
        new_version: { number: 2, rereview: ["IERC"], kept: ["ITSO"], blocked: null },
      },
    }),
    viewer: owner,
    capabilities: ["cite", "create_version", "replace_manuscript", "edit_details"],
    sections: ["overview", "paper", "review", "files"],
  },
  {
    name: "on the adviser-first model, without the server's offer, the owner is not offered the legacy resubmit",
    record: record({ pipeline_status: "in_review", workflow_state: "awaiting_resubmission" }),
    viewer: owner,
    capabilities: ["cite", "edit_details"],
    sections: ["overview", "paper", "review", "files"],
  },
  {
    name: "an accepted Proposal offers no Proposal completion and no continuation yet",
    record: record({
      record_type_name: "Proposal",
      record_type: "Proposal",
      pipeline_status: "approved",
      workflow_state: "approved",
      abstract_file: null,
    }),
    viewer: adviser,
    capabilities: ["cite"],
    sections: ["overview"],
  },
];

describe("the capabilities adapter", () => {
  it("returns the server's list even when client-side role and workflow fields suggest otherwise", () => {
    const payload = Object.assign(record({
      pipeline_status: "draft",
      workflow_state: "draft",
      routing: { accept_and_route: true, route_as: "itso" },
      my_seats: [seat("assigned")],
    }), { capabilities: ["cite", "attach_file"] as Capability[] });

    expect([...capabilitiesFor(payload, stranger)]).toEqual(["cite", "attach_file"]);
  });

  it.each(ROWS)("$name", ({ record: r, viewer, capabilities, sections }) => {
    // The server supplies the action list; these rows still exercise every
    // section-access state and verify that the adapter preserves each list.
    expect([...capabilitiesFor({ ...r, capabilities }, viewer)].sort()).toEqual([...capabilities].sort());
    expect(sectionsFor(r, viewer)).toEqual(sections);
  });

  it("Open review records the seat not yet opened, and only that one", () => {
    expect(seatToOpen(record({ my_seats: [seat("done", 1), seat("assigned", 2)] }))?.id).toBe(2);
    expect(seatToOpen(record({ my_seats: [seat("in_review")] }))).toBeNull();
    expect(seatToOpen(record())).toBeNull();
  });

});
