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
import { useReadingHighlights } from "./useReadingHighlights";
import { useReadingNote } from "./useReadingNote";
import type { HighlightEntry } from "@/api/library";
import type { ReadableHighlight } from "./useReadingHighlights";

const api = vi.hoisted(() => ({
  note: vi.fn(), saveNote: vi.fn(),
  highlights: vi.fn(), saveHighlight: vi.fn(), deleteHighlight: vi.fn(),
}));
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

function Harness({ onAsk, onOpenHighlight = () => {}, openableVersions = [] }: {
  onAsk?: () => void;
  onOpenHighlight?: (h: ReadableHighlight) => void;
  openableVersions?: number[];
}) {
  const state = useReadingNote(record.id, true, 50);
  const highlights = useReadingHighlights(record.id, true);
  return (
    <NotesPanel
      record={record} note={state} onClose={() => {}} onOpenAsk={onAsk}
      highlights={highlights} onOpenHighlight={onOpenHighlight}
      canOpenVersion={(n) => openableVersions.includes(n)}
    />
  );
}

const editor = () => screen.getByRole("textbox", { name: "Your note on this paper" }) as HTMLTextAreaElement;

beforeEach(() => {
  Object.values(api).forEach((fn) => fn.mockReset());
  api.note.mockResolvedValue(note("", 0));
  api.highlights.mockResolvedValue({ data: { results: [] } });
});

const highlight = (over: Partial<Extract<HighlightEntry, { available: true }>> = {}): HighlightEntry => ({
  id: 1, record_id: 7, available: true, state: "current", page: 3,
  quote: "Rainfall explained 62% of the variance in discharge.", prefix: "", suffix: "",
  regions: [{ page: 3, left: 0.1, top: 0.2, right: 0.9, bottom: 0.23 }], open_version: null,
  created_at: "2026-11-12T00:00:00Z", ...over,
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

describe("highlights (IR-583)", () => {
  const list = (...results: HighlightEntry[]) => api.highlights.mockResolvedValue({ data: { results } });
  const highlightsSection = () => screen.findByRole("region", { name: "Highlights" });

  it("says how to make one when there are none", async () => {
    renderScreen(<Harness />);

    const section = await highlightsSection();

    expect(within(section).getByText(/select text in the paper/i)).toBeInTheDocument();
  });

  it("lists each saved passage with its page, apart from the note editor", async () => {
    list(highlight(), highlight({ id: 2, page: 5, quote: "A second passage." }));
    renderScreen(<Harness />);

    const section = await highlightsSection();

    expect(within(section).getByText(/rainfall explained 62%/i)).toBeInTheDocument();
    expect(within(section).getByText("Page 3")).toBeInTheDocument();
    expect(within(section).getByText("Page 5")).toBeInTheDocument();
    expect(within(section).queryByRole("textbox")).not.toBeInTheDocument();
    expect(editor()).toHaveValue("");
  });

  it("opens a current highlight on its own page and region", async () => {
    const user = userEvent.setup();
    const onOpen = vi.fn();
    list(highlight());
    renderScreen(<Harness onOpenHighlight={onOpen} />);

    await user.click(await within(await highlightsSection()).findByRole("button", { name: /^Open page 3/ }));

    expect(onOpen).toHaveBeenCalledWith(expect.objectContaining({ id: 1, page: 3, state: "current" }));
  });

  it("says a highlight is from an earlier version, in words, and does not offer to open it on the paper shown", async () => {
    list(highlight({ state: "stale", open_version: null }));
    renderScreen(<Harness />);

    const section = await highlightsSection();

    expect(within(section).getByText(/earlier version of this paper/i)).toBeInTheDocument();
    expect(within(section).getByText(/rainfall explained 62%/i)).toBeInTheDocument();
    expect(within(section).queryByRole("button", { name: /^Open/ })).not.toBeInTheDocument();
  });

  it("opens a stale highlight in the version that still has its bytes, when the reader may open it", async () => {
    const user = userEvent.setup();
    const onOpen = vi.fn();
    list(highlight({ state: "stale", open_version: 1 }));
    renderScreen(<Harness onOpenHighlight={onOpen} openableVersions={[1]} />);

    await user.click(await within(await highlightsSection()).findByRole("button", { name: /^Open page 3 in v1/ }));

    expect(onOpen).toHaveBeenCalledWith(expect.objectContaining({ state: "stale", open_version: 1 }));
  });

  it("does not offer a version the reader may not open", async () => {
    list(highlight({ state: "stale", open_version: 1 }));
    renderScreen(<Harness openableVersions={[]} />);

    const section = await highlightsSection();

    expect(within(section).queryByRole("button", { name: /^Open/ })).not.toBeInTheDocument();
  });

  it("removes one, and keeps it on screen with a message if that fails", async () => {
    const user = userEvent.setup();
    list(highlight());
    api.deleteHighlight.mockRejectedValueOnce(new Error("offline")).mockResolvedValueOnce({});
    renderScreen(<Harness />);
    const section = await highlightsSection();

    await user.click(await within(section).findByRole("button", { name: /^Remove highlight/ }));
    expect(await within(section).findByText(/could not remove/i)).toBeInTheDocument();
    expect(within(section).getByText(/rainfall explained 62%/i)).toBeInTheDocument();

    await user.click(within(section).getByRole("button", { name: /^Remove highlight/ }));
    await waitFor(() => expect(within(section).queryByText(/rainfall explained 62%/i)).not.toBeInTheDocument());
    expect(api.deleteHighlight).toHaveBeenLastCalledWith(7, 1);
  });

  it("says when they could not be loaded, and tries again", async () => {
    const user = userEvent.setup();
    api.highlights.mockRejectedValueOnce(new Error("offline"));
    renderScreen(<Harness />);

    expect(await screen.findByText(/could not load your highlights/i)).toBeInTheDocument();
    list(highlight());
    await user.click(screen.getByRole("button", { name: "Try again" }));

    expect(await screen.findByText(/rainfall explained 62%/i)).toBeInTheDocument();
  });

  it("has no serious or critical violations with a current and a stale highlight", async () => {
    list(highlight(), highlight({ id: 2, state: "stale", open_version: 1, quote: "An older passage." }));
    const { container } = renderScreen(<Harness openableVersions={[1]} />);
    await highlightsSection();

    await expectNoBlockingA11yViolations(container);
  });
});

