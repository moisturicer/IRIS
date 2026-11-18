/**
 * Ask about a selection (IR-581): a selected passage fills an editable
 * question under a chip naming the paper, version and page. Nothing is sent
 * until Send, the chip can be removed first, and a refused selection is
 * explained without losing the question.
 */
import { useState } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { MemoryRouter } from "react-router-dom";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { apiClient } from "@/api/client";
import { expectNoBlockingA11yViolations } from "@/test/axe";
import type { RecordDetail } from "@/types/records";
import { SELECTION_QUESTION, SELECTION_REFUSALS, type AskSelection } from "@/features/ai/components/SelectionChip";
import { PaperChatPanel } from "./PaperChatDock";

const record = { id: 7, title: "Flood Prediction in the Mananga Catchment" } as RecordDetail;
const REVISION = "5b0c2f7e-0d8a-4c1e-9d55-1f1d1c0e9a11";
const chosen: AskSelection = {
  recordId: 7, title: record.title, versionLabel: "Version 2", manuscriptRevision: REVISION, page: 4,
  quote: "Rainfall rose by forty percent.",
};
const queued = { protocol: "runs-reader-1", id: "r", conversation_id: "c", state: "queued",
  plan: null, context: null, capabilities: { manual_compaction: false } };
const empty = { protocol: "runs-reader-1", id: "c", revision: 0, runs: [], turns: [] };

function Page({ initial = chosen }: { initial?: AskSelection | null }) {
  const [selection, setSelection] = useState<AskSelection | null>(initial);
  return <MemoryRouter>
    <PaperChatPanel record={record} onClose={() => {}} selection={selection} onSelectionChange={setSelection} />
  </MemoryRouter>;
}

afterEach(() => { vi.restoreAllMocks(); sessionStorage.clear(); });

describe("Ask about a selection", () => {
  it("fills an editable question under a chip naming the paper, version and page, and sends nothing", async () => {
    const post = vi.spyOn(apiClient, "post");
    const { container } = render(<Page />);

    const chip = screen.getByRole("group", { name: /Asking about a selection/ });
    expect(chip).toHaveTextContent(`${record.title} · Version 2 · page 4`);
    expect(chip).toHaveTextContent("Rainfall rose by forty percent.");
    expect(screen.getByRole("textbox", { name: "Ask about this paper" })).toHaveValue(SELECTION_QUESTION);
    expect(post).not.toHaveBeenCalled();
    await expectNoBlockingA11yViolations(container);
  });

  it("sends the selection with the question on Send, then clears the chip", async () => {
    const post = vi.spyOn(apiClient, "post").mockResolvedValue({ data: queued });
    vi.spyOn(apiClient, "get").mockResolvedValue({ data: empty });
    const user = userEvent.setup();
    render(<Page />);

    const box = screen.getByRole("textbox", { name: "Ask about this paper" });
    await user.clear(box);
    await user.type(box, "Why did it rise?");
    await user.click(screen.getByRole("button", { name: "Send message" }));

    await waitFor(() => expect(post).toHaveBeenCalledWith("/ai/runtime/runs", expect.objectContaining({
      question: "Why did it rise?",
      selection: { record_id: 7, manuscript_revision: REVISION, page: 4, quote: "Rainfall rose by forty percent." },
    }), expect.anything()));
    await waitFor(() => expect(screen.queryByRole("group", { name: /Asking about a selection/ })).toBeNull());
  });

  it("asks without the passage once the chip is removed", async () => {
    const post = vi.spyOn(apiClient, "post").mockResolvedValue({ data: queued });
    vi.spyOn(apiClient, "get").mockResolvedValue({ data: empty });
    const user = userEvent.setup();
    render(<Page />);

    await user.click(screen.getByRole("button", { name: "Remove selection" }));
    expect(screen.queryByRole("group", { name: /Asking about a selection/ })).toBeNull();
    await user.click(screen.getByRole("button", { name: "Send message" }));

    await waitFor(() => expect(post).toHaveBeenCalled());
    expect(post.mock.calls[0][1]).not.toHaveProperty("selection");
  });

  it("explains a refused selection and keeps the question and the chip", async () => {
    vi.spyOn(apiClient, "post").mockRejectedValue(Object.assign(new Error("422"), {
      isAxiosError: true, response: { status: 422, data: { status: "selection_version" } } }));
    const user = userEvent.setup();
    render(<Page />);

    await user.click(screen.getByRole("button", { name: "Send message" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(SELECTION_REFUSALS.selection_version);
    expect(screen.getByRole("group", { name: /Asking about a selection/ })).toBeInTheDocument();
    const box = screen.getByRole("textbox", { name: "Ask about this paper" });
    expect(box).toHaveValue(SELECTION_QUESTION);
    expect(box).toBeEnabled();
  });

  it("replays the passage a question was asked about, or that it is gone", async () => {
    sessionStorage.setItem("iris-runtime-paper:undefined:7", "c");
    const run = (id: string, selection: unknown) => ({ ...queued, id, state: "completed", question: `Q ${id}`,
      base_revision: 0, version: 1, depth: "ordinary", awaiting_reader: false, sources_available: true, selection });
    vi.spyOn(apiClient, "get").mockImplementation(async (url) => (String(url).endsWith("/conversations")
      ? { data: { protocol: "runs-reader-1", conversations: [], next: null } }
      : { data: { ...empty, revision: 2,
          runs: [run("a", { available: true, record_id: 7, page: 4, quote: "Rainfall rose by forty percent.",
            manuscript_revision: REVISION, current: false }), run("b", { available: false })],
          turns: [] } }) as never);
    render(<Page initial={null} />);

    expect(await screen.findByText("“Rainfall rose by forty percent.”")).toBeInTheDocument();
    expect(screen.getByText(/Page 4 · selected on an earlier version/)).toBeInTheDocument();
    expect(screen.getByText("Asked about a passage that is no longer available.")).toBeInTheDocument();
  });
});
