/**
 * *Add reviewer* (IR-269, ADR-032 §4): a seat holder brings in a colleague
 * from their own office. Every query goes through the accessible tree.
 */
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { expectNoBlockingA11yViolations } from "@/test/axe";
import { renderScreen, screen, waitFor } from "@/test/render";
import type { AddReviewerOptions } from "@/types/records";

import { AddReviewerDialog } from "./AddReviewerDialog";

const addReviewerOptions = vi.fn();
const addReviewer = vi.fn();

vi.mock("@/api/reviews", () => ({
  seatsApi: {
    addReviewerOptions: (id: number) => addReviewerOptions(id),
    addReviewer: (id: number, reviewer: number) => addReviewer(id, reviewer),
  },
}));

const OPTIONS: AddReviewerOptions = {
  assignment: 31,
  party: "ierc",
  party_label: "IERC",
  members: [
    { id: 61, name: "Iris Erc", seated: true },
    { id: 62, name: "Ivan Erc", seated: false },
  ],
};

beforeEach(() => {
  addReviewerOptions.mockReset().mockResolvedValue({ data: OPTIONS });
  addReviewer.mockReset().mockResolvedValue({ data: {} });
});

describe("AddReviewerDialog", () => {
  it("lists the office's members, someone already reviewing unchoosable, and adds the one picked", async () => {
    const onAdded = vi.fn();
    const { container } = renderScreen(
      <AddReviewerDialog assignmentId={31} onClose={() => {}} onAdded={onAdded} />,
    );

    const picker = await screen.findByRole("combobox", { name: "Reviewer at IERC" });
    expect(screen.getByRole("option", { name: "Iris Erc (already reviewing)" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Add reviewer" })).toBeDisabled();
    await expectNoBlockingA11yViolations(container);

    await userEvent.selectOptions(picker, "62");
    await userEvent.click(screen.getByRole("button", { name: "Add reviewer" }));

    await waitFor(() => expect(onAdded).toHaveBeenCalledWith("Ivan Erc", "IERC"));
    expect(addReviewer).toHaveBeenCalledWith(31, 62);
  });

  it("says why when the server refuses", async () => {
    addReviewer.mockRejectedValue({
      response: { data: { detail: "Ivan Erc already holds a seat on this review." } },
    });
    renderScreen(<AddReviewerDialog assignmentId={31} onClose={() => {}} onAdded={() => {}} />);

    await userEvent.selectOptions(await screen.findByRole("combobox", { name: "Reviewer at IERC" }), "62");
    await userEvent.click(screen.getByRole("button", { name: "Add reviewer" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("already holds a seat");
  });
});
