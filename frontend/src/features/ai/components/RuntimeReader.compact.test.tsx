import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { vi, expect, test, afterEach } from "vitest";
import { expectNoBlockingA11yViolations } from "@/test/axe";
import { apiClient } from "@/api/client";
import { CompactionStatus, RuntimeReader } from "./RuntimeReader";
import type { ReaderConversation, ReaderRun } from "@/api/runtimeReader";

afterEach(() => vi.restoreAllMocks());

const base = { protocol: "runs-reader-1", conversation_id: "c", version: 1, depth: "ordinary", awaiting_reader: false,
  sources_available: true, plan: null, context: null, compaction: null, finished_at: null, turn_id: null,
  base_revision: 3 } as const;
const asked = (n: number) => ({ ...base, id: `ask-${n}`, kind: "ask", state: "completed", question: `Question ${n}?`,
  capabilities: { manual_compaction: true } }) as unknown as ReaderRun;
const compacting = (over: Partial<ReaderRun> = {}) => ({ ...base, id: "compact-1", kind: "compact", state: "running",
  question: "", capabilities: { manual_compaction: true }, ...over }) as unknown as ReaderRun;
const turn = (n: number) => ({ id: `t${n}`, run_id: `ask-${n}`, ordinal: n, question: `Question ${n}?`,
  answer: `Answer ${n}.`, kind: "answer", citations: [] });
const conversation = (runs: ReaderRun[], revision = 3): ReaderConversation => ({
  protocol: "runs-reader-1", id: "c", revision, runs, turns: [1, 2, 3].map(turn) }) as unknown as ReaderConversation;

const history = [asked(1), asked(2), asked(3)];

/** The server: `served` is what a reopen returns, and moves when the compaction is posted. */
function server(initial: ReaderConversation, compaction?: ReaderRun, served = initial) {
  const state = { served: initial };
  const get = vi.spyOn(apiClient, "get").mockImplementation(async (path) => ({
    data: String(path).includes("conversations") ? state.served : compaction ?? initial.runs[0] }));
  const post = vi.spyOn(apiClient, "post").mockImplementation(async (path) => {
    if (String(path).endsWith("/compact")) {
      state.served = served;
      return { data: compaction };
    }
    return { data: compaction };
  });
  return { get, post };
}

function open(props: { recordId?: number } = {}) {
  return render(<MemoryRouter><RuntimeReader conversationId="c" {...props} /></MemoryRouter>);
}

test("a reader with the capability can compact, and the request carries the revision they saw", async () => {
  const user = userEvent.setup();
  const running = compacting();
  const { post } = server(conversation(history), running, conversation([...history, running]));
  const { container } = open({ recordId: 42 });

  const button = await screen.findByRole("button", { name: "Compact conversation" });
  // The action says what it does and what it keeps, to everyone who reaches it.
  expect(button).toHaveAccessibleDescription(/Original answers are kept/);
  await user.click(button);

  await waitFor(() => expect(post).toHaveBeenCalledTimes(1));
  const [path, body, config] = post.mock.calls[0];
  expect(path).toBe("/ai/runtime/conversations/c/compact");
  expect(body).toEqual({ base_revision: 3 });
  // Paper Chat's scope and the reader protocol travel as for any question; the key makes a click one request.
  expect(config?.headers).toMatchObject({ "X-IRIS-Protocol": "runs-reader-1", "X-IRIS-Record": "42" });
  expect(String((config?.headers as Record<string, string>)["Idempotency-Key"])).toHaveLength(36);

  expect(await screen.findByText("Compacting conversation")).toBeInTheDocument();
  // While it runs the reader can stop it, and nothing else can start beside it.
  expect(screen.getByRole("button", { name: "Stop compaction" })).toBeEnabled();
  expect(screen.queryByRole("button", { name: "Compact conversation" })).not.toBeInTheDocument();
  expect(screen.getByRole("textbox")).toBeDisabled();
  await expectNoBlockingA11yViolations(container);
});

test("no compaction control is offered where the deployment cannot compact", async () => {
  const off = history.map(run => ({ ...run, capabilities: { manual_compaction: false } }) as ReaderRun);
  server(conversation(off));
  open();
  expect(await screen.findByText("Answer 3.")).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: /compact/i })).not.toBeInTheDocument();
});

test("nothing is offered before there is anything to condense", async () => {
  server({ ...conversation([asked(1)]), turns: [] });
  open();
  await waitFor(() => expect(screen.getByRole("textbox")).toBeEnabled());
  expect(screen.queryByRole("button", { name: /compact/i })).not.toBeInTheDocument();
});

test("a double click is one request", async () => {
  const user = userEvent.setup();
  const running = compacting();
  const { post } = server(conversation(history), running, conversation([...history, running]));
  open();
  await user.dblClick(await screen.findByRole("button", { name: "Compact conversation" }));
  expect(await screen.findByText("Compacting conversation")).toBeInTheDocument();
  expect(post).toHaveBeenCalledTimes(1);
});

test("a compaction that finished says so, keeps the originals and offers it again", async () => {
  const done = compacting({ state: "completed", compaction: { compactions: 1, turns_compacted: 2, last: "compacted" },
    context: { estimated: true, used_tokens: 900, capacity_tokens: 1000 } });
  server(conversation([...history, done]));
  const { container } = open();
  const status = await screen.findByRole("region", { name: "Conversation compaction" });
  expect(within(status).getByText("Conversation compacted")).toBeInTheDocument();
  expect(status).toHaveTextContent("Original answers are kept");
  expect(status).toHaveTextContent("Estimated context: 900 of 1,000 tokens");
  // The originals are still on the page, and never described as removed.
  expect(screen.getByText("Answer 1.")).toBeInTheDocument();
  expect(container).not.toHaveTextContent(/deleted|removed|erased/i);
  expect(screen.getByRole("button", { name: "Compact conversation" })).toBeInTheDocument();
  await expectNoBlockingA11yViolations(container);
});

test.each([
  ["failed", "Compaction unavailable"], ["expired", "Compaction unavailable"],
  ["cancelled", "Compaction stopped"], ["conflict", "Conversation changed"],
])("a %s compaction leaves the conversation as it was", async (state, message) => {
  server(conversation([...history, compacting({ state } as Partial<ReaderRun>)]));
  open();
  const status = await screen.findByRole("region", { name: "Conversation compaction" });
  expect(status).toHaveTextContent(message);
  expect(status).toHaveTextContent(state === "conflict" ? /Reconnect/ : /conversation is unchanged/i);
  expect(screen.getByText("Answer 3.")).toBeInTheDocument();
});

test("nothing older to condense is a plain answer, not a failure", () => {
  render(<CompactionStatus run={compacting({ state: "completed",
    compaction: { compactions: 0, turns_compacted: 0, last: "kept" } })} />);
  expect(screen.getByText(/Nothing older to condense yet/)).toBeInTheDocument();
  expect(screen.queryByText("Compaction unavailable")).not.toBeInTheDocument();
});

test("a lapsed session waits for the reader to reconnect", () => {
  render(<CompactionStatus run={compacting({ state: "queued", awaiting_reader: true })} />);
  expect(screen.getByText("Compacting conversation")).toBeInTheDocument();
  expect(screen.getByText("Reconnect to continue.")).toBeInTheDocument();
});

test("Stop ends a running compaction, by keyboard", async () => {
  const user = userEvent.setup();
  const running = compacting();
  const { post } = server(conversation([...history, running]));
  post.mockResolvedValue({ data: { ...running, state: "cancelled" } });
  open();
  (await screen.findByRole("button", { name: "Stop compaction" })).focus();
  await user.keyboard("{Enter}");
  expect(await screen.findByText(/Compaction stopped/)).toBeInTheDocument();
  expect(post.mock.calls[0][0]).toBe("/ai/runtime/runs/compact-1/cancel");
});

test("another run in the conversation shows that run, not an error", async () => {
  const user = userEvent.setup();
  const live = { ...asked(4), state: "running" } as ReaderRun;
  const { get } = server(conversation(history));
  const post = vi.spyOn(apiClient, "post").mockRejectedValue({ isAxiosError: true, response: { status: 409 } });
  open();
  const button = await screen.findByRole("button", { name: "Compact conversation" });
  get.mockImplementation(async () => ({ data: conversation([...history, live], 3) }));
  await user.click(button);
  await waitFor(() => expect(post).toHaveBeenCalledTimes(1));
  expect(await screen.findByRole("button", { name: "Stop research" })).toBeInTheDocument();
  expect(screen.queryByRole("alert")).not.toBeInTheDocument();
});

test("a conversation that moved on asks the reader to reconnect before compacting again", async () => {
  const user = userEvent.setup();
  server(conversation(history));
  const post = vi.spyOn(apiClient, "post").mockRejectedValue({ isAxiosError: true, response: { status: 409 } });
  open();
  await user.click(await screen.findByRole("button", { name: "Compact conversation" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("conversation changed");
  await user.click(screen.getByRole("button", { name: "Reconnect" }));
  await waitFor(() => expect(screen.getByRole("button", { name: "Compact conversation" })).toBeEnabled());
  expect(post).toHaveBeenCalledTimes(1);
});

test("a busy answer keeps the same request for Reconnect", async () => {
  const user = userEvent.setup();
  const running = compacting();
  server(conversation(history), running, conversation([...history, running]));
  const post = vi.spyOn(apiClient, "post")
    .mockRejectedValueOnce({ isAxiosError: true, response: { status: 503, data: { status: "busy" } } })
    .mockResolvedValue({ data: running });
  open();
  await user.click(await screen.findByRole("button", { name: "Compact conversation" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("busy");
  await user.click(screen.getByRole("button", { name: "Reconnect" }));
  await waitFor(() => expect(post).toHaveBeenCalledTimes(2));
  expect(post.mock.calls[0]).toEqual(post.mock.calls[1]);
});

test("a compaction run is never shown as a question, and shows no internals", async () => {
  server(conversation([...history, compacting({ state: "completed",
    compaction: { compactions: 1, turns_compacted: 2, last: "compacted" } })]));
  const { container } = open();
  await screen.findByRole("region", { name: "Conversation compaction" });
  expect(screen.getAllByRole("article", { name: "Research question" })).toHaveLength(3);
  expect(container).not.toHaveTextContent(/handoff|revision|summary text|opaque|reasoning/i);
});
