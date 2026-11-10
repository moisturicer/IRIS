/**
 * Saved replies (ADR-032 §7 Conveniences, IR-877): a person's own texts,
 * inserted into a comment box. Inserting only adds text, so whatever is
 * selected in the box stays. Every query goes through the accessible tree.
 */
import userEvent from "@testing-library/user-event";
import { useRef, useState } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { expectNoBlockingA11yViolations } from "@/test/axe";
import { renderScreen, screen, within } from "@/test/render";
import type { SavedReply } from "@/types/reviews";

import { SavedReplies } from "./SavedReplies";

const api = vi.hoisted(() => ({
  savedReplies: vi.fn(),
  createSavedReply: vi.fn(),
  updateSavedReply: vi.fn(),
  deleteSavedReply: vi.fn(),
}));
vi.mock("@/api/reviews", () => ({ reviewsApi: api }));

const reply = (id: number, title: string, body: string): SavedReply => ({
  id, title, body, created_at: "2026-11-10T00:00:00Z", updated_at: "2026-11-10T00:00:00Z",
});

beforeEach(() => {
  Object.values(api).forEach((fn) => fn.mockReset());
  api.savedReplies.mockResolvedValue({
    data: { results: [reply(1, "Cite the source", "Please cite this."), reply(2, "Typo", "Typo here.")], limit: 50 },
  });
});

function Box({ initial = "" }: { initial?: string }) {
  const [body, setBody] = useState(initial);
  const ref = useRef<HTMLTextAreaElement>(null);
  return (
    <>
      <label htmlFor="box">Comment</label>
      <textarea id="box" ref={ref} value={body} onChange={(e) => setBody(e.target.value)} />
      <SavedReplies textareaRef={ref} value={body} onChange={setBody} />
    </>
  );
}

const box = () => screen.getByRole("textbox", { name: "Comment" }) as HTMLTextAreaElement;

describe("inserting a saved reply", () => {
  it("inserts at the end of a box nobody has clicked into", async () => {
    const user = userEvent.setup();
    renderScreen(<Box initial="Thanks. " />);

    await user.click(screen.getByRole("button", { name: "Saved replies" }));
    await user.click(await screen.findByRole("button", { name: "Insert “Typo”" }));

    expect(box().value).toBe("Thanks. Typo here.");
    await vi.waitFor(() => expect(box()).toHaveFocus());
    // The menu closes once a reply is used.
    expect(screen.queryByRole("button", { name: "Insert “Typo”" })).not.toBeInTheDocument();
  });

  it("inserts at the cursor once the person has been in the box", async () => {
    const user = userEvent.setup();
    renderScreen(<Box initial="Dear authors, ok" />);
    await user.click(box());
    box().setSelectionRange(14, 14);

    await user.click(screen.getByRole("button", { name: "Saved replies" }));
    await user.click(await screen.findByRole("button", { name: "Insert “Typo”" }));

    expect(box().value).toBe("Dear authors, Typo here.ok");
  });

  it("never replaces selected text: it inserts after the selection", async () => {
    const user = userEvent.setup();
    renderScreen(<Box initial="Keep this text" />);
    await user.click(box());
    box().setSelectionRange(5, 9); // "this"

    await user.click(screen.getByRole("button", { name: "Saved replies" }));
    await user.click(await screen.findByRole("button", { name: "Insert “Typo”" }));

    expect(box().value).toBe("Keep thisTypo here. text");
  });

  it("says when there are none yet", async () => {
    api.savedReplies.mockResolvedValue({ data: { results: [], limit: 50 } });
    const user = userEvent.setup();
    renderScreen(<Box />);

    await user.click(screen.getByRole("button", { name: "Saved replies" }));

    expect(await screen.findByText("No saved replies yet.")).toBeInTheDocument();
  });

  it("treats a response of the wrong shape as a failed load", async () => {
    api.savedReplies.mockResolvedValue({ data: { results: "not a list" } });
    const user = userEvent.setup();
    renderScreen(<Box initial="Kept" />);

    await user.click(screen.getByRole("button", { name: "Saved replies" }));

    expect(await screen.findByText("Your saved replies couldn’t be loaded.")).toBeInTheDocument();
    expect(box().value).toBe("Kept");
  });

  it("leaves out an entry of the wrong shape and keeps the rest", async () => {
    api.savedReplies.mockResolvedValue({
      data: { results: [{ id: 3 }, reply(2, "Typo", "Typo here.")], limit: 50 },
    });
    const user = userEvent.setup();
    renderScreen(<Box />);

    await user.click(screen.getByRole("button", { name: "Saved replies" }));

    expect(await screen.findByRole("button", { name: "Insert “Typo”" })).toBeInTheDocument();
    expect(screen.getAllByRole("button", { name: /^Insert/ })).toHaveLength(1);
  });

  it("has no blocking accessibility violations when open", async () => {
    const user = userEvent.setup();
    const { container } = renderScreen(<Box />);
    await user.click(screen.getByRole("button", { name: "Saved replies" }));
    await screen.findByRole("button", { name: "Insert “Typo”" });

    await expectNoBlockingA11yViolations(container);
  });
});

describe("managing saved replies", () => {
  async function openManager() {
    const user = userEvent.setup();
    renderScreen(<Box />);
    await user.click(screen.getByRole("button", { name: "Saved replies" }));
    await user.click(await screen.findByRole("button", { name: "Manage saved replies" }));
    return { user, dialog: await screen.findByRole("dialog", { name: "Saved replies" }) };
  }

  it("adds a reply, which is then offered for inserting", async () => {
    api.createSavedReply.mockResolvedValue({ data: reply(3, "Methods", "Say more about the method.") });
    const { user, dialog } = await openManager();

    await user.type(within(dialog).getByRole("textbox", { name: "Title" }), "Methods");
    await user.type(within(dialog).getByRole("textbox", { name: "Text" }), "Say more about the method.");
    await user.click(within(dialog).getByRole("button", { name: "Save reply" }));

    expect(api.createSavedReply).toHaveBeenCalledWith({ title: "Methods", body: "Say more about the method." });
    expect(await within(dialog).findByRole("listitem", { name: "Methods" })).toBeInTheDocument();
    await user.click(within(dialog).getByRole("button", { name: "Done" }));
    expect(await screen.findByRole("button", { name: "Insert “Methods”" })).toBeInTheDocument();
  });

  it("shows the server's refusal and keeps what was typed", async () => {
    api.createSavedReply.mockRejectedValue({
      isAxiosError: true,
      response: { status: 400, data: { title: ["You already have a saved reply with that title."] } },
    });
    const { user, dialog } = await openManager();

    await user.type(within(dialog).getByRole("textbox", { name: "Title" }), "typo");
    await user.type(within(dialog).getByRole("textbox", { name: "Text" }), "Again.");
    await user.click(within(dialog).getByRole("button", { name: "Save reply" }));

    expect(await within(dialog).findByRole("alert")).toHaveTextContent(
      "You already have a saved reply with that title.",
    );
    expect(within(dialog).getByRole("textbox", { name: "Title" })).toHaveValue("typo");
  });

  it("edits a reply's title and text", async () => {
    api.updateSavedReply.mockResolvedValue({ data: reply(2, "Typo", "There's a typo here.") });
    const { user, dialog } = await openManager();
    const item = within(dialog).getByRole("listitem", { name: "Typo" });

    await user.click(within(item).getByRole("button", { name: "Edit “Typo”" }));
    const text = within(item).getByRole("textbox", { name: "Text" });
    await user.clear(text);
    await user.type(text, "There's a typo here.");
    await user.click(within(item).getByRole("button", { name: "Save changes" }));

    expect(api.updateSavedReply).toHaveBeenCalledWith(2, { title: "Typo", body: "There's a typo here." });
    expect(await within(dialog).findByText("There's a typo here.")).toBeInTheDocument();
  });

  it("deletes a reply only after asking", async () => {
    api.deleteSavedReply.mockResolvedValue({ data: undefined });
    const { user, dialog } = await openManager();
    const item = within(dialog).getByRole("listitem", { name: "Typo" });

    await user.click(within(item).getByRole("button", { name: "Delete “Typo”" }));
    expect(api.deleteSavedReply).not.toHaveBeenCalled();
    await user.click(within(item).getByRole("button", { name: "Yes, delete" }));

    expect(api.deleteSavedReply).toHaveBeenCalledWith(2);
    await vi.waitFor(() =>
      expect(within(dialog).queryByRole("listitem", { name: "Typo" })).not.toBeInTheDocument(),
    );
  });
});
