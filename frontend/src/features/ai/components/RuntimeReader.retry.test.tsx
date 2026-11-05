import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { vi, expect, test, afterEach } from "vitest";
import { apiClient } from "@/api/client";
import { RuntimeReader } from "./RuntimeReader";

afterEach(() => vi.restoreAllMocks());

const run = (over: Record<string, unknown> = {}) => ({
  protocol: "runs-reader-1", id: "run-1", conversation_id: "conversation-1", kind: "ask", question: "Compare",
  state: "cancelled", version: 2, depth: "ordinary", base_revision: 0, awaiting_reader: false,
  retry_of: null, retried_by: null, cursor: 3, plan: null, context: null,
  capabilities: { manual_compaction: false }, ...over,
});

/** The server's view of the conversation; a test moves it on by assigning `server.latest`. */
const server = { latest: run(), revision: 0 };

function reopened(latest: ReturnType<typeof run>, revision = 0) {
  Object.assign(server, { latest, revision });
  vi.spyOn(apiClient, "get").mockImplementation(async (path) => ({ data: String(path).includes("conversations")
    ? { protocol: "runs-reader-1", id: "conversation-1", revision: server.revision, runs: [server.latest], turns: [] }
    : server.latest }));
}

test("a stopped question can be asked again as a new linked run, once", async () => {
  const retried = run({ id: "run-2", state: "queued", retry_of: "run-1" });
  reopened(run());
  const post = vi.spyOn(apiClient, "post").mockImplementation(async () => {
    server.latest = retried;
    return { data: retried };
  });
  const user = userEvent.setup();
  render(<MemoryRouter><RuntimeReader conversationId="conversation-1" /></MemoryRouter>);

  await user.click(await screen.findByRole("button", { name: "Try this question again" }));
  await waitFor(() => expect(post).toHaveBeenCalledWith("/ai/runtime/runs/run-1/retry", {},
    expect.objectContaining({ headers: expect.objectContaining({
      "X-IRIS-Protocol": "runs-reader-1", "Idempotency-Key": expect.stringMatching(/.{8,}/) }) })));
  expect(await screen.findByRole("button", { name: "Stop research" })).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "Try this question again" })).not.toBeInTheDocument();
  expect(post).toHaveBeenCalledTimes(1);
});

test.each([
  ["answered", run({ state: "completed" }), 1],
  ["already retried", run({ retried_by: "run-2" }), 0],
  ["after the conversation moved on", run(), 1],
  ["still running", run({ state: "running" }), 0],
  ["a condensing run, which asks nothing", run({ kind: "compact", question: "" }), 0],
])("no retry is offered for a run that is %s", async (_name, latest, revision) => {
  reopened(latest, revision);
  render(<MemoryRouter><RuntimeReader conversationId="conversation-1" /></MemoryRouter>);
  await screen.findByRole("textbox");
  await waitFor(() => expect(apiClient.get).toHaveBeenCalled());
  expect(screen.queryByRole("button", { name: "Try this question again" })).not.toBeInTheDocument();
});

test("a retry that cannot start says the conversation changed and offers to reconnect", async () => {
  reopened(run());
  vi.spyOn(apiClient, "post").mockRejectedValue({ isAxiosError: true, response: { status: 409, data: { status: "conflict" } } });
  const user = userEvent.setup();
  render(<MemoryRouter><RuntimeReader conversationId="conversation-1" /></MemoryRouter>);
  await user.click(await screen.findByRole("button", { name: "Try this question again" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("changed");
  expect(screen.getByRole("button", { name: "Reconnect" })).toBeInTheDocument();
});
