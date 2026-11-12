/**
 * *Submit new version* (IR-273, ADR-032 §5): the confirmation names who
 * reviews the version and whose clearance is kept, in the server's words,
 * and a refusal is shown as the server words it. Every query goes through
 * the accessible tree, by role and accessible name.
 */
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { expectNoBlockingA11yViolations } from "@/test/axe";
import { useUIStore } from "@/store/ui.store";
import { renderScreen, screen, waitFor, within } from "@/test/render";
import type { NewVersionHint } from "@/types/records";

import { NewVersionDialog, newVersionSummary } from "./NewVersionDialog";

const submitNewVersion = vi.fn();

vi.mock("@/api/records", () => ({
  recordsApi: {
    submitNewVersion: (id: number) => submitNewVersion(id),
  },
}));

const HINT: NewVersionHint = { number: 3, rereview: ["IERC"], kept: ["ITSO"], blocked: null };

function open(hint: NewVersionHint = HINT, newManuscript = false) {
  const onClose = vi.fn();
  const onDone = vi.fn();
  const view = renderScreen(
    <NewVersionDialog recordId={7} hint={hint} newManuscript={newManuscript} onClose={onClose} onDone={onDone} />,
  );
  return { onClose, onDone, view };
}

beforeEach(() => {
  useUIStore.setState({ toasts: [] });
  submitNewVersion.mockReset().mockResolvedValue({ data: {} });
});

describe("newVersionSummary", () => {
  it("names who reviews the version and whose clearance is kept, as the card words it", () => {
    expect(newVersionSummary(HINT)).toBe("IERC will review v3. ITSO's clearance is kept.");
  });

  it("joins several parties, and says nothing is kept under the restart-all policy", () => {
    expect(newVersionSummary({ number: 2, rereview: ["IERC", "KTTO"], kept: ["ITSO", "RDCO Final"], blocked: null }))
      .toBe("IERC and KTTO will review v2. ITSO and RDCO Final keep their clearances.");
    expect(newVersionSummary({ number: 2, rereview: ["IERC"], kept: [], blocked: null }))
      .toBe("IERC will review v2.");
  });
});

describe("NewVersionDialog", () => {
  it("confirms who reviews it before anything is sent", async () => {
    const { view } = open();

    const dialog = screen.getByRole("dialog", { name: "Submit new version" });
    expect(dialog).toHaveTextContent("IERC will review v3. ITSO's clearance is kept.");
    expect(submitNewVersion).not.toHaveBeenCalled();
    await expectNoBlockingA11yViolations(view.container);
  });

  it("says when a revised manuscript goes with it", () => {
    open(HINT, true);
    expect(screen.getByRole("dialog", { name: "Submit new version" }))
      .toHaveTextContent("Your revised manuscript and any details you edited go with it.");
  });

  it("submits, and reports it", async () => {
    const { onDone } = open();

    await userEvent.click(screen.getByRole("button", { name: "Submit v3" }));

    expect(submitNewVersion).toHaveBeenCalledWith(7);
    await waitFor(() => expect(onDone).toHaveBeenCalledWith(expect.stringContaining("v3 submitted")));
  });

  it("shows the server's refusal and stays open", async () => {
    submitNewVersion.mockRejectedValue({
      response: { data: { detail: "Nothing has changed since IERC asked for a revision." } },
    });
    const { onDone } = open();

    await userEvent.click(screen.getByRole("button", { name: "Submit v3" }));

    // A toast, not a line inside the dialog.
    await waitFor(() => expect(useUIStore.getState().toasts).toHaveLength(1));
    expect(useUIStore.getState().toasts[0]).toMatchObject({
      type: "error",
      persist: true,
      message: "Nothing has changed since IERC asked for a revision.",
    });
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    expect(onDone).not.toHaveBeenCalled();
    expect(screen.getByRole("dialog", { name: "Submit new version" })).toBeInTheDocument();
  });
});

describe("the response to reviewers (IR-876)", () => {
  const entry = (over: Partial<NonNullable<NewVersionHint["letter"]>[number]>) => ({
    thread: 1, party: "ierc", party_label: "IERC", severity: "must_fix" as const,
    comment: "Add the consent form.", version: 2, page: 4, quote: "consent", answer: null, note: "", ...over,
  });
  const LETTER: NewVersionHint = {
    ...HINT,
    letter: [
      entry({ thread: 1, answer: "addressed", note: "Appendix C." }),
      entry({ thread: 2, severity: "suggestion", comment: "Consider a diagram.", answer: null }),
      entry({ thread: 3, severity: "suggestion", comment: "Shorten the title.", answer: "declined", note: "The college requires it." }),
    ],
  };

  it("shows the letter the version will carry, each answer as given", async () => {
    const { view } = open(LETTER);

    const letter = screen.getByRole("region", { name: "Response to reviewers" });
    const items = within(letter).getAllByRole("listitem");
    expect(items).toHaveLength(3);
    expect(items[0]).toHaveTextContent("Must fix");
    expect(items[0]).toHaveTextContent("Add the consent form.");
    expect(items[0]).toHaveTextContent("Addressed: Appendix C.");
    expect(items[1]).toHaveTextContent("No answer given");
    expect(items[2]).toHaveTextContent("Declined: The college requires it.");
    await expectNoBlockingA11yViolations(view.container);
  });

  it("holds Submit, saying why, while a Must fix has no answer", () => {
    open({ ...LETTER, blocked: "Answer each open Must fix thread first: 1 thread from IERC." });

    const submit = screen.getByRole("button", { name: "Submit v3" });
    expect(submit).toBeDisabled();
    expect(submit).toHaveAccessibleDescription("Answer each open Must fix thread first: 1 thread from IERC.");
  });

  it("says nothing about a letter when the version answers no thread", () => {
    open({ ...HINT, letter: [] });
    expect(screen.queryByRole("region", { name: "Response to reviewers" })).not.toBeInTheDocument();
  });
});
