/**
 * Discover after Proposals left the public catalogue (IR-264, ADR-021 §13).
 *
 * The server does the real work: `PUBLICLY_VISIBLE_STATUSES` is published only,
 * so the list endpoint never returns an approved or completed Proposal. These
 * tests cover what the client still presented as if it would:
 *
 *   - a "Proposal" record-type filter, which could now only ever return nothing;
 *   - a "Research Ongoing" badge, which described an approved Proposal as
 *     public, in-progress research.
 *
 * Every query goes through the accessible tree, by role and accessible name.
 */
import { beforeEach, describe, expect, it, vi } from "vitest";

import { expectNoBlockingA11yViolations } from "@/test/axe";
import { renderScreen, screen, userEvent, within } from "@/test/render";
import type { RecordListItem } from "@/types/records";

import DiscoverPage from "./DiscoverPage";

function listItem(overrides: Partial<RecordListItem>): RecordListItem {
  return {
    id: 1,
    title: "Untitled",
    abstract: "An abstract.",
    year_accomplished: 2026,
    classification_name: "Applied Research",
    record_type_name: "Thesis/Research",
    pipeline_status: "published",
    is_ip: false,
    ip_type: "",
    for_commercialization: false,
    community_extension: false,
    access_count: 0,
    file_count: 0,
    created_at: "2026-09-01T08:00:00Z",
    authors: [{ id: 1, name: "Mateo Villanueva", role: null }],
    ...overrides,
  };
}

const publishedThesis = listItem({ id: 1, title: "Assistive Navigation for Low-Vision Commuters" });

/**
 * Not something the API returns any more. Fed in deliberately, to prove the
 * card itself no longer calls an approved Proposal "ongoing research" -- the
 * guard is on the client too, not only on what the server happens to send.
 */
const approvedProposal = listItem({
  id: 2,
  title: "Low-Cost Soil Moisture Sensing for Upland Farms",
  record_type_name: "Proposal",
  pipeline_status: "approved",
});

let listed: RecordListItem[] = [publishedThesis];

const page = <T,>(results: T[]) => Promise.resolve({ data: { results, count: results.length } });

vi.mock("@/api/records", () => ({
  recordsApi: {
    list: vi.fn(() => page(listed)),
    classifications: vi.fn(() => page([{ id: 1, name: "Applied Research" }])),
    recordTypes: vi.fn(() =>
      page([
        { id: 1, name: "Thesis/Research" },
        { id: 2, name: "Project" },
        { id: 3, name: "Proposal" },
      ]),
    ),
  },
}));

vi.mock("@/api/accounts", () => ({
  accountsApi: { colleges: vi.fn(() => page([{ id: 1, name: "College of Engineering" }])) },
}));

vi.mock("@/api/notifications", () => ({
  notificationsApi: {
    list: vi.fn(() => page([])),
    unreadCount: vi.fn(() => Promise.resolve({ data: { count: 0 } })),
    markRead: vi.fn(),
    markAllRead: vi.fn(),
  },
}));

beforeEach(() => {
  vi.clearAllMocks();
  listed = [publishedThesis];
});

async function openRecordTypeFilter() {
  await userEvent.click(await screen.findByRole("button", { name: /^filter/i }));
  await userEvent.click(await screen.findByRole("button", { name: /any record type/i }));
  return screen.findByRole("listbox");
}

describe("Discover without Proposals", () => {
  it("does not offer a Proposal record-type filter", async () => {
    const { container } = renderScreen(<DiscoverPage />, { route: "/discover" });

    const options = await openRecordTypeFilter();
    expect(within(options).getByRole("option", { name: /thesis\/research/i })).toBeInTheDocument();
    expect(within(options).getByRole("option", { name: /project/i })).toBeInTheDocument();
    expect(within(options).queryByRole("option", { name: /proposal/i })).not.toBeInTheDocument();

    await expectNoBlockingA11yViolations(container);
  });

  it("does not present an approved Proposal as ongoing research", async () => {
    listed = [publishedThesis, approvedProposal];
    renderScreen(<DiscoverPage />, { route: "/discover" });

    await screen.findByText(approvedProposal.title);
    expect(screen.queryByText(/research ongoing/i)).not.toBeInTheDocument();
  });

  it("still lists a published thesis", async () => {
    renderScreen(<DiscoverPage />, { route: "/discover" });
    expect(await screen.findByText(publishedThesis.title)).toBeInTheDocument();
  });
});
