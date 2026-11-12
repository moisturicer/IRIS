/**
 * Private notes in the reading workspace (IR-580, ADR-064).
 *
 * What this pins: an empty note says who can read it; autosave announces
 * Saving, then Saved, and a failure never shows Saved and never clears the
 * draft; a revision conflict keeps both texts, pauses autosave and makes the
 * reader choose; a note that could not be loaded cannot be overwritten; and
 * leaving with an unsaved draft asks first. Every query goes through the
 * accessible tree.
 */
import userEvent from "@testing-library/user-event";
import { act } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { expectNoBlockingA11yViolations } from "@/test/axe";
import { renderScreen, screen, waitFor, within } from "@/test/render";
import type { RecordDetail } from "@/types/records";

import { NotesPanel } from "./NotesPanel";
import { useReadingNote } from "./useReadingNote";

const api = vi.hoisted(() => ({ note: vi.fn(), saveNote: vi.fn() }));
vi.mock("@/api/library", async (original) => ({
  ...(await original<typeof import("@/api/library")>()),
  libraryApi: api,
}));

const record = { id: 7, title: "Flood Prediction in the Mananga Catchment" } as RecordDetail;

const note = (body: string, revision: number) => ({ data: { body, revision, updated_at: "2026-11-12T00:00:00Z" } });
const conflict = (body: string, revision: number) =>
  Object.assign(new Error("conflict"), {
    isAxiosError: true,
    response: { status: 409, data: { code: "revision_conflict", body, revision } },
  });

function Harness({ onAsk }: { onAsk?: () => void }) {
  const state = useReadingNote(record.id, true, 5);
  return <NotesPanel record={record} note={state} onClose={() => {}} onOpenAsk={onAsk} />;
}

const editor = () => screen.getByRole("textbox", { name: "Your note on this paper" }) as HTMLTextAreaElement;

beforeEach(() => {
  Object.values(api).forEach((fn) => fn.mockReset());
  api.note.mockResolvedValue(note("", 0));
});

describe("opening Notes", () => {
  it("says the note is private and offers an empty editor", async () => {
    const { container } = renderScreen(<Harness />);

    expect(await screen.findByRole("heading", { name: "Notes" })).toBeInTheDocument();
    expect(screen.getByText(/only you can read/i)).toBeInTheDocument();
    await waitFor(() => expect(editor()).toHaveValue(""));
    expect(editor()).toHaveAttribute("placeholder", expect.stringMatching(/./));
    await expectNoBlockingA11yViolations(container);
  });

  it("shows what the reader wrote before", async () => {
    api.note.mockResolvedValue(note("Method looks thin.", 3));
    renderScreen(<Harness />);

    await waitFor(() => expect(editor()).toHaveValue("Method looks thin."));
    expect(api.saveNote).not.toHaveBeenCalled();
  });

  it("does not offer an editor, and so cannot overwrite, when the note could not be loaded", async () => {
    const user = userEvent.setup();
    api.note.mockRejectedValueOnce(new Error("offline"));
    renderScreen(<Harness />);

    expect(await screen.findByText("Could not load your note.")).toBeInTheDocument();
    expect(screen.queryByRole("textbox", { name: "Your note on this paper" })).not.toBeInTheDocument();

    api.note.mockResolvedValueOnce(note("Still here.", 2));
    await user.click(screen.getByRole("button", { name: "Try again" }));
    await waitFor(() => expect(editor()).toHaveValue("Still here."));
    expect(api.saveNote).not.toHaveBeenCalled();
  });
});

describe("autosave", () => {
  it("saves what was typed against the revision it started from, and says so", async () => {
    const user = userEvent.setup();
    api.note.mockResolvedValue(note("First.", 1));
    api.saveNote.mockResolvedValueOnce(note("First. Second.", 2)).mockResolvedValueOnce(note("First. Second. Third.", 3));
    renderScreen(<Harness />);
    await waitFor(() => expect(editor()).toHaveValue("First."));

    await user.type(editor(), " Second.");
    await waitFor(() => expect(screen.getByRole("status")).toHaveTextContent("Saved"));
    await user.type(editor(), " Third.");
    await waitFor(() => expect(api.saveNote).toHaveBeenCalledTimes(2));

    expect(api.saveNote).toHaveBeenNthCalledWith(1, 7, { body: "First. Second.", base_revision: 1 });
    expect(api.saveNote).toHaveBeenNthCalledWith(2, 7, { body: "First. Second. Third.", base_revision: 2 });
  });

  it("says Saving while a save is in flight, and never Saved before it lands", async () => {
    const user = userEvent.setup();
    let land!: (value: ReturnType<typeof note>) => void;
    api.saveNote.mockReturnValueOnce(new Promise((resolve) => { land = resolve; }));
    renderScreen(<Harness />);
    await waitFor(() => expect(editor()).toHaveValue(""));

    await user.type(editor(), "Hello");

    await waitFor(() => expect(screen.getByRole("status")).toHaveTextContent("Saving"));
    expect(screen.getByRole("status")).not.toHaveTextContent("Saved");
    await act(async () => land(note("Hello", 1)));
    expect(screen.getByRole("status")).toHaveTextContent("Saved");
  });

  it("keeps the draft and never says Saved when a save fails, and Try again saves it", async () => {
    const user = userEvent.setup();
    api.saveNote.mockRejectedValueOnce(new Error("offline")).mockResolvedValueOnce(note("Keep me.", 1));
    renderScreen(<Harness />);
    await waitFor(() => expect(editor()).toHaveValue(""));

    await user.type(editor(), "Keep me.");

    await waitFor(() => expect(screen.getByRole("status")).toHaveTextContent("Could not save"));
    expect(screen.getByRole("status")).not.toHaveTextContent(/^Saved/);
    expect(editor()).toHaveValue("Keep me.");

    await user.click(screen.getByRole("button", { name: "Try again" }));
    await waitFor(() => expect(screen.getByRole("status")).toHaveTextContent("Saved"));
    expect(api.saveNote).toHaveBeenLastCalledWith(7, { body: "Keep me.", base_revision: 0 });
    expect(editor()).toHaveValue("Keep me.");
  });

  it("asks before leaving with a draft that is not saved, and not otherwise", async () => {
    const user = userEvent.setup();
    api.saveNote.mockRejectedValue(new Error("offline"));
    renderScreen(<Harness />);
    await waitFor(() => expect(editor()).toHaveValue(""));
    const leave = () => {
      const event = new Event("beforeunload", { cancelable: true });
      window.dispatchEvent(event);
      return event.defaultPrevented;
    };
    expect(leave()).toBe(false);

    await user.type(editor(), "unsaved");
    await waitFor(() => expect(screen.getByRole("status")).toHaveTextContent("Could not save"));

    expect(leave()).toBe(true);
  });
});

describe("a revision conflict", () => {
  async function conflicted() {
    const user = userEvent.setup();
    api.note.mockResolvedValue(note("", 0));
    api.saveNote.mockRejectedValueOnce(conflict("Written on the lab PC.", 4));
    renderScreen(<Harness />);
    await waitFor(() => expect(editor()).toHaveValue(""));
    await user.type(editor(), "Written at home.");
    await screen.findByText(/changed on another device/i);
    return user;
  }

  it("keeps both texts on screen and stops autosaving until the reader chooses", async () => {
    await conflicted();

    const both = within(screen.getByRole("region", { name: "Note changed on another device" }));
    expect(both.getByText("Written on the lab PC.")).toBeInTheDocument();
    expect(both.getByText("Written at home.")).toBeInTheDocument();
    expect(screen.getByRole("status")).not.toHaveTextContent(/^Saved/);
    await new Promise((resolve) => setTimeout(resolve, 30));
    expect(api.saveNote).toHaveBeenCalledTimes(1);
  });

  it("combines both texts into the editor and saves them against the server's revision", async () => {
    const user = await conflicted();
    // The server echoes what it stored.
    api.saveNote.mockResolvedValueOnce(note("Written on the lab PC.\n\nWritten at home.", 5));

    await user.click(screen.getByRole("button", { name: "Keep both" }));

    await waitFor(() => expect(api.saveNote).toHaveBeenCalledTimes(2));
    expect(api.saveNote).toHaveBeenLastCalledWith(7, {
      body: "Written on the lab PC.\n\nWritten at home.", base_revision: 4,
    });
    expect(editor()).toHaveValue("Written on the lab PC.\n\nWritten at home.");
    expect(screen.queryByText(/changed on another device/i)).not.toBeInTheDocument();
  });

  it("keeps this device's text, deliberately, against the server's revision", async () => {
    const user = await conflicted();
    api.saveNote.mockResolvedValueOnce(note("Written at home.", 5));

    await user.click(screen.getByRole("button", { name: "Keep this device’s text" }));

    await waitFor(() => expect(api.saveNote).toHaveBeenCalledTimes(2));
    expect(api.saveNote).toHaveBeenLastCalledWith(7, { body: "Written at home.", base_revision: 4 });
  });

  it("takes the saved text and drops this device's draft only when the reader says so", async () => {
    const user = await conflicted();

    await user.click(screen.getByRole("button", { name: "Use the saved note" }));

    expect(editor()).toHaveValue("Written on the lab PC.");
    expect(api.saveNote).toHaveBeenCalledTimes(1);
    expect(screen.queryByText(/changed on another device/i)).not.toBeInTheDocument();
  });
});

describe("the panel", () => {
  it("offers a way to Ask IRIS, which shares its place", async () => {
    const user = userEvent.setup();
    const onAsk = vi.fn();
    renderScreen(<Harness onAsk={onAsk} />);

    await user.click(await screen.findByRole("button", { name: "Ask IRIS" }));

    expect(onAsk).toHaveBeenCalled();
  });
});
