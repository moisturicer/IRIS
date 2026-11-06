/** A review comment for tests: a sent, open Adviser Suggestion unless told otherwise. */
import type { ReviewComment } from "@/types/records";

let nextId = 1;
export function comment(over: Partial<ReviewComment> = {}): ReviewComment {
  return {
    id: nextId++, author: 7, author_name: "Ana Reyes", body: "A point.", version: 1, reply_to: null,
    created_at: "2026-11-01T00:00:00Z", edited_at: null, can_edit: false,
    party: "adviser", party_label: "Adviser", severity: "suggestion", is_draft: false, round: null,
    anchor: null, state: "open", resolved_by: null, resolved_at: null, closed_by_decision: null,
    closed_reason: null, answer: null, events: [],
    can_delete: false, can_change_severity: false, can_resolve: false, can_reopen: false, can_answer: false,
    ...over,
  };
}

