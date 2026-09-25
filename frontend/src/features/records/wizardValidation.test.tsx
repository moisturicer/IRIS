/**
 * Two wizard defects found while taking IR-360's screenshots, both on main
 * before it.
 *
 * - Continuing past Submit Disclosure's first step with no type chosen said
 *   "Expected string, received null": an untouched radio group is null, and
 *   the schema gave Zod no message for a value of the wrong type.
 * - Edit Record's type select showed "Select record type" for a record that
 *   has one. The select mounts before its options arrive, so the browser
 *   could not select the saved value, although the form still held it.
 */
import { beforeEach, describe, expect, it, vi } from "vitest";
import { Route, Routes } from "react-router-dom";

import { renderScreen, screen, userEvent } from "@/test/render";

import AddRecordPage from "./AddRecordPage";
import EditRecordPage from "./EditRecordPage";

vi.mock("@/api/records", () => ({
  recordsApi: {
    recordTypes: vi.fn(),
    classifications: vi.fn(),
    pscedList: vi.fn(),
    detail: vi.fn(),
  },
}));

vi.mock("@/api/accounts", () => ({
  accountsApi: { listAdvisers: vi.fn() },
}));

vi.mock("@/api/documents", () => ({
  documentsApi: { slots: vi.fn() },
}));

const { recordsApi } = await import("@/api/records");
const { accountsApi } = await import("@/api/accounts");
const { documentsApi } = await import("@/api/documents");

function page<T>(results: T[]) {
  return { data: { count: results.length, next: null, previous: null, results } };
}

beforeEach(() => {
  vi.mocked(recordsApi.recordTypes).mockResolvedValue(
    page([{ id: 1, name: "Proposal" }, { id: 2, name: "Thesis / Research" }]) as never,
  );
  vi.mocked(recordsApi.classifications).mockResolvedValue(page([]) as never);
  vi.mocked(recordsApi.pscedList).mockResolvedValue(page([]) as never);
  vi.mocked(accountsApi.listAdvisers).mockResolvedValue(page([]) as never);
  vi.mocked(documentsApi.slots).mockResolvedValue({ data: [] } as never);
  vi.mocked(recordsApi.detail).mockResolvedValue({
    data: {
      title: "A study of clearance-aware resubmission",
      abstract: "An abstract long enough to pass the thirty-character rule.",
      year_accomplished: 2026,
      record_type: 2,
      authors: [{ name: "A. Author" }],
      keywords: [],
      owners: [],
    },
  } as never);
});

describe("Submit Disclosure — continuing with no type chosen", () => {
  it("says a type is required, in words a submitter can act on", async () => {
    const user = userEvent.setup();
    renderScreen(<AddRecordPage />);

    await screen.findByRole("radio", { name: /Thesis \/ Research/ });
    await user.click(screen.getByRole("button", { name: /Continue to Details/ }));

    expect(await screen.findByText("Record type is required.")).toBeInTheDocument();
    expect(screen.queryByText(/Expected string/)).not.toBeInTheDocument();
  });
});

describe("Edit Record — the saved record type", () => {
  it("shows the saved type in the select, not the placeholder", async () => {
    const user = userEvent.setup();
    renderScreen(
      <Routes>
        <Route path="/records/:id/edit" element={<EditRecordPage />} />
      </Routes>,
      { route: "/records/5/edit" },
    );

    await user.click(await screen.findByRole("button", { name: "Next" }));

    expect(await screen.findByDisplayValue("Thesis / Research")).toBeInTheDocument();
    expect(screen.queryByDisplayValue("Select record type")).not.toBeInTheDocument();
  });
});
