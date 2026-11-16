import { useState } from "react";
import { act, render, renderHook, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { vi, expect, test, afterEach } from "vitest";
import { expectNoBlockingA11yViolations } from "@/test/axe";
import { apiClient } from "@/api/client";
import { runtimeReader } from "@/api/runtimeReader";
import { useConversationHistory } from "../hooks/useConversationHistory";
import { ConversationHistoryList } from "./ConversationSidebar";

afterEach(() => vi.restoreAllMocks());

/** Answers the runtime list from `pages`, in order, and Django's earlier-conversations list with none. */
function serve(...pages: unknown[]) {
  const queue = [...pages];
  return vi.spyOn(apiClient, "get").mockImplementation(async (url) =>
    (url === "/ai/conversations/" ? { data: [] } : (queue.length > 1 ? queue.shift() : queue[0])) as never);
}

const reply = (titles: string[], next: string | null = null) => ({ data: {
  protocol: "runs-reader-1", next,
  conversations: titles.map(title => ({ id: `id-${title}`, title, record_id: null, updated_at: "2026-11-01T10:00:00+00:00" })),
} });

function History({ activeId }: { activeId?: string }) {
  const api = useState(() => runtimeReader())[0];
  const history = useConversationHistory(api, activeId);
  return <MemoryRouter>
    <ConversationHistoryList conversations={history.conversations} activeId={activeId ?? null}
      search={history.search} onDelete={() => undefined} />
  </MemoryRouter>;
}

test("the search box has an accessible name, searches by keyboard and says plainly when nothing matches", async () => {
  const get = serve(reply(["Flood methods"]));
  const user = userEvent.setup();
  const { container } = render(<History />);
  await screen.findByRole("link", { name: /Flood methods/ });
  get.mockImplementation(async (url) => (url === "/ai/conversations/" ? { data: [] } : reply([])) as never);
  await user.type(screen.getByRole("searchbox", { name: "Search your past conversations" }), "tracer dye");
  expect(await screen.findByText("No conversations match “tracer dye”.")).toBeInTheDocument();
  expect(get).toHaveBeenLastCalledWith("/ai/runtime/conversations", expect.objectContaining({
    params: { q: "tracer dye" },
    headers: expect.objectContaining({ "X-IRIS-Protocol": "runs-reader-1" }),
  }));
  await expectNoBlockingA11yViolations(container);
});

test("a reader with no conversations is told so, not that a search failed", async () => {
  serve(reply([]));
  render(<History />);
  expect(await screen.findByText("Your past chats will appear here.")).toBeInTheDocument();
});

test("Load more reaches older conversations and keeps the search", async () => {
  const get = serve(reply(["First"], "cursor-1"), reply(["Older"]));
  const user = userEvent.setup();
  render(<History />);
  await screen.findByRole("link", { name: /First/ });
  await user.click(screen.getByRole("button", { name: "Load more" }));
  expect(await screen.findByRole("link", { name: /Older/ })).toBeInTheDocument();
  expect(screen.getByRole("link", { name: /First/ })).toBeInTheDocument();
  expect(get).toHaveBeenLastCalledWith("/ai/runtime/conversations", expect.objectContaining({ params: { before: "cursor-1" } }));
  expect(screen.queryByRole("button", { name: "Load more" })).not.toBeInTheDocument();
});

test("a failed load says so", async () => {
  vi.spyOn(apiClient, "get").mockImplementation(async (url) => { if (url === "/ai/conversations/") return { data: [] }; throw new Error("down"); });
  render(<History />);
  expect(await screen.findByText(/Could not load your conversations/)).toBeInTheDocument();
});

test("a late answer to an older search is ignored", async () => {
  const get = vi.spyOn(apiClient, "get").mockResolvedValueOnce(reply(["First"]));
  const api = runtimeReader();
  const { result } = renderHook(() => useConversationHistory(api));
  await waitFor(() => expect(result.current.conversations).toHaveLength(1));
  let release: (value: unknown) => void = () => {};
  get.mockImplementationOnce(() => new Promise(resolve => { release = resolve; }));
  get.mockResolvedValue(reply(["Current"]));
  act(() => result.current.search.onText("x"));
  await waitFor(() => expect(get).toHaveBeenCalledTimes(2));
  act(() => result.current.search.onText("xy"));
  await waitFor(() => expect(result.current.conversations.map(c => c.title)).toEqual(["Current"]));
  release(reply(["Stale"]));
  await new Promise(resolve => setTimeout(resolve, 20));
  expect(result.current.conversations.map(c => c.title)).toEqual(["Current"]);
});

test("opening a listed conversation keeps the pages loaded; a new one reloads the list", async () => {
  const get = vi.spyOn(apiClient, "get")
    .mockResolvedValueOnce(reply(["First"], "cursor-1"))
    .mockResolvedValueOnce(reply(["Older"]));
  const api = runtimeReader();
  const { result, rerender } = renderHook(({ active }) => useConversationHistory(api, active), {
    initialProps: { active: "id-First" },
  });
  await waitFor(() => expect(result.current.conversations).toHaveLength(1));
  await act(async () => { result.current.search.onMore(); });
  await waitFor(() => expect(result.current.conversations).toHaveLength(2));
  rerender({ active: "id-Older" });
  expect(get).toHaveBeenCalledTimes(2);
  expect(result.current.conversations).toHaveLength(2);
  get.mockResolvedValue(reply(["Brand new", "First"]));
  rerender({ active: "id-Brand new" });
  await waitFor(() => expect(result.current.conversations.map(c => c.title)).toEqual(["Brand new", "First"]));
  expect(result.current.titleOf("id-Older")).toBe("Older");
});
