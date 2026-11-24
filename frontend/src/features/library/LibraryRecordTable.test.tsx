/**
 * A citation is for published work (IR-1305). A saved Proposal or unpublished
 * paper has no Cite action in the Library; a published one keeps it. A list
 * item carries no `capabilities`, so the table mirrors the server's `cite` rule.
 */
import { describe, expect, it, vi } from "vitest";

import { renderScreen, screen } from "@/test/render";
import type { RecordListItem } from "@/types/records";

import { LibraryRecordTable } from "./LibraryRecordTable";

const paper = (overrides: Partial<RecordListItem>): RecordListItem => ({
  id: 1, title: "A paper", abstract: "An abstract.", year_accomplished: 2026, classification_name: "Applied Research",
  record_type_name: "Thesis/Research", pipeline_status: "published", is_ip: false, ip_type: "",
  for_commercialization: false, community_extension: false, access_count: 0, file_count: 0,
  created_at: "2026-09-01T08:00:00Z", authors: [{ id: 1, name: "Mateo Villanueva", role: null }],
  ...overrides,
});

const PUBLISHED = paper({ id: 1, title: "Flood prediction in the Mananga catchment" });
const PROPOSAL = paper({
  id: 2, title: "Soil moisture sensing for upland farms", record_type_name: "Proposal", pipeline_status: "approved",
});

describe("LibraryRecordTable's Cite (IR-1305)", () => {
  it.each(["list", "grid"] as const)("in the %s layout, offers Cite on a published paper only", (layout) => {
    renderScreen(
      <LibraryRecordTable
        records={[PUBLISHED, PROPOSAL]}
        layout={layout}
        query=""
        selected={new Set()}
        onToggleSelect={vi.fn()}
        onToggleAll={vi.fn()}
        onCite={vi.fn()}
        onRemove={vi.fn()}
      />,
    );

    expect(screen.getByRole("button", { name: `Cite ${PUBLISHED.title}` })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: `Cite ${PROPOSAL.title}` })).not.toBeInTheDocument();
    // Removing a saved Proposal from the Library still works.
    expect(screen.getByRole("button", { name: `Remove from library: ${PROPOSAL.title}` })).toBeInTheDocument();
  });
});
