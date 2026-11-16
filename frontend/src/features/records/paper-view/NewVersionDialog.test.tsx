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
import type { NewVersionHint, RecordDetail } from "@/types/records";

import { NewVersionDialog, newVersionSummary } from "./NewVersionDialog";

const submitNewVersion = vi.fn();
const detail = vi.fn();

vi.mock("@/api/records", () => ({
  recordsApi: {
    submitNewVersion: (id: number) => submitNewVersion(id),
    detail: (id: number) => detail(id),
  },
}));

const HINT: NewVersionHint = { number: 3, rereview: ["IERC"], kept: ["ITSO"], blocked: null };

function open(hint: NewVersionHint = HINT, newManuscript = false) {
  const onClose = vi.fn();
  const onDone = vi.fn();
  const onRefreshed = vi.fn();
  const view = renderScreen(
    <NewVersionDialog
      recordId={7}
      hint={hint}
      newManuscript={newManuscript}
      onClose={onClose}
      onDone={onDone}
      onRefreshed={onRefreshed}
    />,
  );
  return { onClose, onDone, onRefreshed, view };
}

/** The record as a re-read finds it: its versions, and the hint while a request is open. */
function reread(versions: number[], hint: NewVersionHint | null = HINT): RecordDetail {
  return {
    id: 7,
    versions: versions.map((number) => ({ number })),
    revision: { new_version: hint },
  } as unknown as RecordDetail;
}

beforeEach(() => {
  useUIStore.setState({ toasts: [] });
  submitNewVersion.mockReset().mockResolvedValue({ data: {} });
  detail.mockReset().mockResolvedValue({ data: reread([1, 2]) });
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
    // The server said why, so there is nothing to check.
    expect(detail).not.toHaveBeenCalled();
  });
});

/*
 * IR-1049: on the deployed site v2 was saved and the answer still failed, so
 * the owner was told to try again and the retry was refused. An answer with no
 * reason from the server says nothing about whether the version went in, so the
 * dialog reads the record again before it says anything.
 */
describe("a failure the server gives no reason for (IR-1049)", () => {
  const SERVER_ERROR = { response: { status: 500, data: "<h1>Server Error (500)</h1>" } };
  const GATEWAY_TIMEOUT = { response: { status: 504, data: "" } };

  it("reports the version submitted when the record shows it was saved", async () => {
    submitNewVersion.mockRejectedValue(SERVER_ERROR);
    detail.mockResolvedValue({ data: reread([1, 2, 3], null) });
    const { onDone } = open();

    await userEvent.click(screen.getByRole("button", { name: "Submit v3" }));

    expect(detail).toHaveBeenCalledWith(7);
    await waitFor(() => expect(onDone).toHaveBeenCalledWith(
      "v3 submitted. The reviewers who asked for changes have been notified.",
    ));
    expect(useUIStore.getState().toasts).toHaveLength(0);
  });

  it("does the same after a gateway timeout", async () => {
    submitNewVersion.mockRejectedValue(GATEWAY_TIMEOUT);
    detail.mockResolvedValue({ data: reread([1, 2, 3], null) });
    const { onDone } = open();

    await userEvent.click(screen.getByRole("button", { name: "Submit v3" }));

    await waitFor(() => expect(onDone).toHaveBeenCalledWith(expect.stringContaining("v3 submitted")));
  });

  it("invites a retry only once the record shows the version was not saved", async () => {
    submitNewVersion.mockRejectedValue(SERVER_ERROR);
    const fresh = reread([1, 2]);
    detail.mockResolvedValue({ data: fresh });
    const { onDone, onRefreshed } = open();

    await userEvent.click(screen.getByRole("button", { name: "Submit v3" }));

    await waitFor(() => expect(useUIStore.getState().toasts).toHaveLength(1));
    expect(useUIStore.getState().toasts[0]).toMatchObject({
      type: "error",
      message: "The new version could not be submitted. Please try again.",
    });
    // The page shows the record as it now stands.
    expect(onRefreshed).toHaveBeenCalledWith(fresh);
    expect(onDone).not.toHaveBeenCalled();
  });

  it("says the record moved on, without inviting a retry, when no revision is asked for any more", async () => {
    submitNewVersion.mockRejectedValue(SERVER_ERROR);
    const fresh = reread([1, 2], null);
    detail.mockResolvedValue({ data: fresh });
    const { onDone, onRefreshed } = open();

    await userEvent.click(screen.getByRole("button", { name: "Submit v3" }));

    await waitFor(() => expect(useUIStore.getState().toasts).toHaveLength(1));
    const { message } = useUIStore.getState().toasts[0];
    expect(message).toBe("The new version could not be submitted. The page now shows where the record stands.");
    expect(message).not.toMatch(/try again/i);
    expect(onRefreshed).toHaveBeenCalledWith(fresh);
    expect(onDone).not.toHaveBeenCalled();
  });

  it("asks the owner to reload before retrying when the record cannot be read either", async () => {
    submitNewVersion.mockRejectedValue(new Error("Network Error"));
    detail.mockRejectedValue(new Error("Network Error"));
    const { onDone, onRefreshed } = open();

    await userEvent.click(screen.getByRole("button", { name: "Submit v3" }));

    await waitFor(() => expect(useUIStore.getState().toasts).toHaveLength(1));
    expect(useUIStore.getState().toasts[0]).toMatchObject({
      type: "error",
      persist: true,
      message: "The page couldn't confirm whether v3 was submitted. Reload the page to check before trying again.",
    });
    expect(onDone).not.toHaveBeenCalled();
    expect(onRefreshed).not.toHaveBeenCalled();
  });

  it("keeps Submit busy while it checks", async () => {
    submitNewVersion.mockRejectedValue(SERVER_ERROR);
    let answer: (value: unknown) => void = () => {};
    detail.mockReturnValue(new Promise((resolve) => { answer = resolve; }));
    const { onDone } = open();

    await userEvent.click(screen.getByRole("button", { name: "Submit v3" }));

    await waitFor(() => expect(detail).toHaveBeenCalled());
    expect(screen.getByRole("button", { name: "Cancel" })).toBeDisabled();
    answer({ data: reread([1, 2, 3], null) });
    await waitFor(() => expect(onDone).toHaveBeenCalled());
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
