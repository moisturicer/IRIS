/** A Call as the API sends it, for tests (IR-765). Every flag off unless given. */
import type { Opportunity } from "@/types/opportunities";

export function callFixture(overrides: Partial<Opportunity> = {}): Opportunity {
  const id = overrides.id ?? 1;
  return {
    id,
    opportunity_type: "conference",
    type_display: "Conference",
    title: `Call ${id}`,
    description: "Full papers on computing education.",
    external_url: "https://example.org/call",
    due_date: "2026-12-01",
    location: "Cebu City, Philippines",
    areas: [1],
    area_names: ["Artificial Intelligence"],
    start_date: null,
    end_date: null,
    registration_fee: "",
    is_featured: false,
    posted_by: 3,
    posted_by_name: "Ana Reyes",
    created_at: "2026-11-10T00:00:00Z",
    updated_at: "2026-11-10T00:00:00Z",
    days_left: 15,
    is_closed: false,
    papers_state: "accepting",
    papers_label: "Accepting papers",
    event_state: null,
    event_label: null,
    status: "pending",
    status_label: "Waiting for RDCO",
    review_reason: "",
    reviewed_at: null,
    can_edit: false,
    can_delete: false,
    can_remove: false,
    can_confirm: false,
    can_reject: false,
    can_feature: false,
    edit_returns_to_pending: false,
    ...overrides,
  };
}
