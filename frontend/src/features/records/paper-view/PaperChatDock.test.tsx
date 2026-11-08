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

    expect(screen.getByText("Research stays within this paper.")).toBeInTheDocument();
    await user.type(screen.getByRole("textbox", { name: "Ask about this paper" }), "What was measured?");
    await user.click(screen.getByRole("button", { name: "Send message" }));

    await waitFor(() => expect(post).toHaveBeenCalledWith("/ai/runtime/runs",
      expect.objectContaining({ question: "What was measured?" }),
      expect.objectContaining({ headers: expect.objectContaining({ "X-IRIS-Record": "7" }) })));
    expect(post.mock.calls.every(([url]) => String(url).startsWith("/ai/runtime/"))).toBe(true);
    await expectNoBlockingA11yViolations(container);
  });
});
