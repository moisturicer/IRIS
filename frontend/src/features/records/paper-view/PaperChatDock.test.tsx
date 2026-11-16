/**
 * Paper Chat on the AI runtime (IR-957): Django's Paper Chat is retired, so
 * the panel is the runtime reader scoped to the paper it opened on.
 */
import { afterEach, describe, expect, it, vi } from "vitest";
import { MemoryRouter } from "react-router-dom";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { apiClient } from "@/api/client";
import { expectNoBlockingA11yViolations } from "@/test/axe";
import type { RecordDetail } from "@/types/records";
import { PaperChatPanel } from "./PaperChatDock";

const record = { id: 7, title: "Flood Prediction in the Mananga Catchment" } as RecordDetail;

afterEach(() => vi.restoreAllMocks());

describe("Paper Chat", () => {
  it("asks the runtime about this paper alone, and never Django", async () => {
    const post = vi.spyOn(apiClient, "post").mockResolvedValue({ data: {
      protocol: "runs-reader-1", id: "r", conversation_id: "c", state: "queued",
      plan: null, context: null, capabilities: { manual_compaction: false } } });
    vi.spyOn(apiClient, "get").mockResolvedValue({ data: {
      protocol: "runs-reader-1", id: "c", revision: 0, runs: [], turns: [] } });
    const user = userEvent.setup();
    const { container } = render(<MemoryRouter><PaperChatPanel record={record} onClose={() => {}} /></MemoryRouter>);

    expect(screen.getByText("Ask about this paper.")).toBeInTheDocument();
    await user.type(screen.getByRole("textbox", { name: "Ask about this paper" }), "What was measured?");
    await user.click(screen.getByRole("button", { name: "Send message" }));

    await waitFor(() => expect(post).toHaveBeenCalledWith("/ai/runtime/runs",
      expect.objectContaining({ question: "What was measured?" }),
      expect.objectContaining({ headers: expect.objectContaining({ "X-IRIS-Record": "7" }) })));
    expect(post.mock.calls.every(([url]) => String(url).startsWith("/ai/runtime/"))).toBe(true);
    await expectNoBlockingA11yViolations(container);
  });

  it("downloads its conversation as Markdown, scoped to the paper (IR-1167)", async () => {
    sessionStorage.setItem("iris-runtime-paper:undefined:7", "c");
    const get = vi.spyOn(apiClient, "get").mockImplementation(async (url) => (String(url).endsWith("/export")
      ? { data: new Blob(["# Notes"]), headers: { "content-disposition": 'attachment; filename="Notes.md"' } }
      : String(url).endsWith("/conversations")
        ? { data: { protocol: "runs-reader-1", conversations: [], next: null } }
        : { data: { protocol: "runs-reader-1", id: "c", revision: 0, runs: [], turns: [] } }) as never);
    Object.assign(URL, { createObjectURL: vi.fn(() => "blob:x"), revokeObjectURL: vi.fn() });
    const click = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {});
    const user = userEvent.setup();
    render(<MemoryRouter><PaperChatPanel record={record} onClose={() => {}} /></MemoryRouter>);
    await user.click(screen.getByRole("button", { name: "Download conversation as Markdown" }));
    await waitFor(() => expect(click).toHaveBeenCalled());
    expect(get).toHaveBeenCalledWith("/ai/runtime/conversations/c/export", expect.objectContaining({
      responseType: "blob", headers: expect.objectContaining({ "X-IRIS-Record": "7" }) }));
    sessionStorage.clear();
  });
});
