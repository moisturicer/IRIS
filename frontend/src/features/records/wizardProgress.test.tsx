/**
 * Step progress without colour (IR-360), in both wizards.
 *
 * A step is done, current or upcoming. Done was the only green thing on the
 * screen; in the palette it is near-black, the same as plain text. So each
 * state has a signal that is not a colour: done steps show a check and say
 * "completed" to a screen reader, the current step is `aria-current="step"`,
 * and an upcoming step shows only its number.
 */
import { beforeEach, describe, expect, it, vi } from "vitest";
import { Route, Routes } from "react-router-dom";

import { renderScreen, screen, userEvent, within } from "@/test/render";

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
  vi.mocked(recordsApi.recordTypes).mockResolvedValue(page([{ id: 2, name: "Thesis / Research" }]) as never);
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

function expectDone(step: HTMLElement) {
  expect(step).toHaveTextContent(/completed/i);
  expect(step.querySelector("i.fa-check")).toHaveAttribute("aria-hidden");
}

function expectUpcoming(step: HTMLElement) {
  expect(step).not.toHaveTextContent(/completed/i);
  expect(step.querySelector("i.fa-check")).toBeNull();
  expect(step).not.toHaveAttribute("aria-current");
  expect(step.querySelector('[aria-current="step"]')).toBeNull();
}

describe("Submit Disclosure — step progress", () => {
  it("tells done, current and upcoming apart without colour", async () => {
    const user = userEvent.setup();
    renderScreen(<AddRecordPage />);

    await user.click(await screen.findByRole("radio", { name: /Thesis \/ Research/ }));
    await user.click(screen.getByRole("button", { name: /Continue to Details/ }));

    const [first, second, third] = within(
      screen.getByRole("list", { name: "Submission steps" }),
    ).getAllByRole("listitem");

    expectDone(first);
    expect(second.querySelector('[aria-current="step"]')).toHaveTextContent("Details");
    expectUpcoming(third);
  });
});

describe("Edit Record — step progress", () => {
  it("tells done, current and upcoming apart without colour", async () => {
    const user = userEvent.setup();
    renderScreen(
      <Routes>
        <Route path="/records/:id/edit" element={<EditRecordPage />} />
      </Routes>,
      { route: "/records/5/edit" },
    );

    const titleStep = await screen.findByRole("button", { name: /Title & Abstract/ });
    expect(titleStep).toHaveAttribute("aria-current", "step");

    await user.click(screen.getByRole("button", { name: "Next" }));

    const done = await screen.findByRole("button", { name: /Title & Abstract/ });
    expectDone(done);
    expect(done).not.toHaveAttribute("aria-current");
    expect(screen.getByRole("button", { name: /Details/ })).toHaveAttribute("aria-current", "step");
    expectUpcoming(screen.getByRole("button", { name: /Documents/ }));
  });
});
