import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { vi, expect, test, afterEach } from "vitest";
import { expectNoBlockingA11yViolations } from "@/test/axe";
import { apiClient } from "@/api/client";
import { RuntimeHistory } from "./RuntimeHistory";

afterEach(() => vi.restoreAllMocks());

const page = (titles: string[], next: string | null = null) => ({ data: {
  protocol: "runs-reader-1", next,
  conversations: titles.map((title, n) => ({ id: `id-${title}`, title, updated_at: `2026-11-0${n + 1}T10:00:00+00:00` })),
} });

const renderHistory = (activeId?: string) =>
  render(<MemoryRouter><RuntimeHistory activeId={activeId} /></MemoryRouter>);

test("lists past conversations as links, marks the open one and has a named search box", async () => {
  vi.spyOn(apiClient, "get").mockResolvedValue(page(["Flood methods", "Pond sampling"]));
  const { container } = renderHistory("id-Pond sampling");
  const list = await screen.findByRole("navigation", { name: "Past conversations" });
  const links = within(list).getAllByRole("link");
  expect(links.map(l => l.getAttribute("href"))).toEqual(["/ai/conversations/id-Flood methods", "/ai/conversations/id-Pond sampling"]);
  expect(screen.getByRole("link", { name: /Pond sampling/ })).toHaveAttribute("aria-current", "page");
  expect(screen.getByRole("searchbox", { name: "Search your past conversations" })).toBeInTheDocument();
  await expectNoBlockingA11yViolations(container);
});

test("typing searches by keyboard and an empty result says so plainly", async () => {
  const get = vi.spyOn(apiClient, "get").mockResolvedValue(page(["Flood methods"]));
  const user = userEvent.setup();
  renderHistory();
  await screen.findByText("Flood methods");
  get.mockResolvedValue(page([]));
  await user.type(screen.getByRole("searchbox"), "tracer dye");
  expect(await screen.findByText("No conversations match “tracer dye”.")).toBeInTheDocument();
  expect(get).toHaveBeenLastCalledWith("/ai/runtime/conversations", expect.objectContaining({
    params: { q: "tracer dye" },
    headers: expect.objectContaining({ "X-IRIS-Protocol": "runs-reader-1" }),
  }));
  expect(screen.queryByRole("navigation", { name: "Past conversations" })).not.toBeInTheDocument();
});

test("a reader with no conversations is told so, not that a search failed", async () => {
  vi.spyOn(apiClient, "get").mockResolvedValue(page([]));
  renderHistory();
  expect(await screen.findByText("Your past chats will appear here.")).toBeInTheDocument();
});

test("Load more pages past the first page and keeps the search", async () => {
  const get = vi.spyOn(apiClient, "get")
    .mockResolvedValueOnce(page(["First"], "cursor-1"))
    .mockResolvedValueOnce(page(["Older"]));
  const user = userEvent.setup();
  renderHistory();
  await screen.findByText("First");
  await user.click(screen.getByRole("button", { name: "Load more" }));
  expect(await screen.findByText("Older")).toBeInTheDocument();
  expect(screen.getByText("First")).toBeInTheDocument();
  expect(get).toHaveBeenLastCalledWith("/ai/runtime/conversations", expect.objectContaining({ params: { before: "cursor-1" } }));
  expect(screen.queryByRole("button", { name: "Load more" })).not.toBeInTheDocument();
});

test("a failed load says so and a late answer to an old search is ignored", async () => {
  const get = vi.spyOn(apiClient, "get").mockRejectedValueOnce(new Error("down"));
  renderHistory();
  expect(await screen.findByRole("alert")).toHaveTextContent("Could not load your conversations");
  let release: (value: unknown) => void = () => {};
  get.mockImplementationOnce(() => new Promise(resolve => { release = resolve; }));
  get.mockResolvedValue(page(["Current"]));
  const user = userEvent.setup();
  await user.type(screen.getByRole("searchbox"), "x");
  await waitFor(() => expect(get).toHaveBeenCalledTimes(2));
  await user.type(screen.getByRole("searchbox"), "y");
  await waitFor(() => expect(screen.getByText("Current")).toBeInTheDocument());
  release(page(["Stale"]));
  await new Promise(resolve => setTimeout(resolve, 20));
  expect(screen.queryByText("Stale")).not.toBeInTheDocument();
  expect(screen.getByText("Current")).toBeInTheDocument();
});
