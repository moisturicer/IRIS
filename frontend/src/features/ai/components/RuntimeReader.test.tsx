import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { vi, expect, test, afterEach } from "vitest";
import { expectNoBlockingA11yViolations } from "@/test/axe";
import { apiClient } from "@/api/client";
import { RuntimeReader } from "./RuntimeReader";

afterEach(() => vi.restoreAllMocks());

test("reader sees persisted work, stops by keyboard and chooses thoroughness for the next request", async () => {
  const queued = { protocol: "runs-reader-1", id: "run-1", conversation_id: "conversation-1", question: "Compare",
    state: "running", version: 1, depth: "ordinary", awaiting_reader: false,
    plan: { revision: 2, steps: [{ id: "compare", title: "Compare methods", status: "in_progress" }] },
    context: null, capabilities: { manual_compaction: false } };
  const stopped = { ...queued, state: "cancelled" };
  const get = vi.spyOn(apiClient, "get").mockImplementation(async (path) => ({ data:
    String(path).includes("conversations") ? { protocol: "runs-reader-1", id: "conversation-1", revision: 0,
      runs: [queued], turns: [] } : queued }));
  const post = vi.spyOn(apiClient, "post").mockImplementation(async (path) => ({ data:
    String(path).endsWith("cancel") ? stopped : queued }));
  const user = userEvent.setup();
  render(<MemoryRouter><RuntimeReader conversationId="conversation-1" /></MemoryRouter>);
  expect(await screen.findByText("Compare methods")).toBeInTheDocument();
  expect(screen.getByText("In progress")).toBeInTheDocument();
  expect(screen.getByText("Context estimate unavailable")).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: /compact/i })).not.toBeInTheDocument();
  expect(screen.getByText(/can make mistakes/)).toBeInTheDocument();
  screen.getByRole("button", { name: "Stop research" }).focus();
  await user.keyboard("{Enter}");
  expect(await screen.findByText("Stopped")).toBeInTheDocument();
  await user.click(screen.getByRole("checkbox", { name: "Be more thorough" }));
  await user.type(screen.getByRole("textbox"), "Compare further");
  await user.click(screen.getByRole("button", { name: "Send message" }));
  await waitFor(() => expect(post).toHaveBeenCalledWith("/ai/runtime/runs", expect.objectContaining({
    question: "Compare further", depth: "deep", conversation_id: "conversation-1", base_revision: 0,
  }), expect.objectContaining({ headers: expect.objectContaining({ "X-IRIS-Protocol": "runs-reader-1" }) })));
  get.mockRestore();
  post.mockRestore();
});

test("a busy submission can reconnect with the same request identity and Paper Chat scope", async () => {
  const user = userEvent.setup();
  const post = vi.spyOn(apiClient, "post").mockRejectedValueOnce(
    { isAxiosError: true, response: { status: 503, data: { status: "busy" } } })
    .mockResolvedValue({ data: { protocol: "runs-reader-1", id: "r", conversation_id: "c",
      state: "queued", plan: null, context: null, capabilities: { manual_compaction: false } } });
  vi.spyOn(apiClient, "get").mockResolvedValue({ data: {
    protocol: "runs-reader-1", id: "c", revision: 0, runs: [], turns: [],
  } });
  const { container } = render(<MemoryRouter><RuntimeReader recordId={42} /></MemoryRouter>);
  await user.type(screen.getByRole("textbox", { name: "Ask about this paper" }), "Explain the paper");
  await user.click(screen.getByRole("button", { name: "Send message" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("busy");
  await user.click(screen.getByRole("button", { name: "Reconnect" }));
  await waitFor(() => expect(post).toHaveBeenCalledTimes(2));
  expect(post.mock.calls[0]).toEqual(post.mock.calls[1]);
  expect(post.mock.calls[0][2]?.headers).toMatchObject({ "X-IRIS-Record": "42" });
  await expectNoBlockingA11yViolations(container);
});

test("a revision conflict restores the draft and reconnects before resubmission", async () => {
  const user = userEvent.setup();
  const snapshot = { protocol: "runs-reader-1", id: "c", revision: 1, runs: [], turns: [] };
  const get = vi.spyOn(apiClient, "get").mockResolvedValue({ data: snapshot });
  const post = vi.spyOn(apiClient, "post").mockRejectedValue({ isAxiosError: true, response: { status: 409 } });
  render(<MemoryRouter><RuntimeReader conversationId="c" /></MemoryRouter>);
  await waitFor(() => expect(screen.getByRole("textbox")).toBeEnabled());
  get.mockResolvedValue({ data: { ...snapshot, revision: 2 } });
  await user.type(screen.getByRole("textbox"), "Compare methods");
  await user.click(screen.getByRole("button", { name: "Send message" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("conversation changed");
  expect(screen.getByRole("textbox")).toHaveValue("Compare methods");
  await user.click(screen.getByRole("button", { name: "Reconnect" }));
  await waitFor(() => expect(screen.getByRole("textbox")).toBeEnabled());
  expect(post).toHaveBeenCalledTimes(1);
  await user.click(screen.getByRole("button", { name: "Send message" }));
  await waitFor(() => expect(post.mock.calls[1][1]).toMatchObject({ base_revision: 2 }));
});
