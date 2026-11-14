/**
 * IR-1078: the two coordinator dialogs that load an office's members offer
 * Try again when that list does not load, and read it again.
 */
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { renderScreen, screen } from "@/test/render";
import type { AddReviewerOptions } from "@/types/records";

import { AssignReviewerDialog } from "./AssignReviewerDialog";
import { ReassignDialog } from "./ReassignDialog";

const assignOptions = vi.fn();

vi.mock("@/api/reviews", () => ({
  seatsApi: {
    assignOptions: (id: number) => assignOptions(id),
    assign: vi.fn(),
    reassign: vi.fn(),
  },
}));

const OPTIONS: AddReviewerOptions = {
  assignment: 31,
  party: "ierc",
  party_label: "IERC",
  members: [{ id: 62, name: "Ivan Erc", seated: false }],
};

const serverFailure = () => Object.assign(new Error("500"), { response: { status: 500 } });

beforeEach(() => {
  assignOptions.mockReset().mockRejectedValueOnce(serverFailure()).mockResolvedValue({ data: OPTIONS });
});

describe.each([
  ["AssignReviewerDialog", () => (
    <AssignReviewerDialog assignmentId={31} recordTitle="A paper" onClose={() => {}} onAssigned={vi.fn()} viewerId={1} />
  )],
  ["ReassignDialog", () => (
    <ReassignDialog seatId={5} assignmentId={31} recordTitle="A paper" holderName="Iris Erc" onClose={() => {}} onReassigned={vi.fn()} />
  )],
] as const)("%s", (_name, dialog) => {
  it("blames IRIS for a server failure, and Try again reads the members again", async () => {
    renderScreen(dialog());

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("Your office's members could not be loaded. IRIS took too long to answer. Try again.");

    await userEvent.click(screen.getByRole("button", { name: "Try again" }));
    expect(await screen.findByRole("option", { name: "Ivan Erc" })).toBeInTheDocument();
    expect(assignOptions).toHaveBeenCalledTimes(2);
  });
});
