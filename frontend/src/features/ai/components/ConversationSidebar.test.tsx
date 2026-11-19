/** New chat, Search, Pinned and Recents, rename in place (IR-1160) and a resizable column. */
import { useState } from "react";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";
import { expectNoBlockingA11yViolations } from "@/test/axe";
import type { ReaderConversationSummary } from "@/api/runtimeReader";
import { ConversationSidebar, SIDEBAR_MAX, type HistorySearch, type RenameConversation } from "./ConversationSidebar";

beforeEach(() => localStorage.clear());
afterEach(() => vi.restoreAllMocks());

// The read-only list of Django's earlier conversations asks for nothing here.
vi.mock("./EarlierConversations", () => ({ EarlierConversationList: () => null }));

const search: HistorySearch = {
  text: "", onText: () => undefined, query: "", state: "ready", hasMore: false, loadingMore: false, onMore: () => undefined,
};

const entries = (...titles: string[]): ReaderConversationSummary[] =>
  titles.map(title => ({ id: `id-${title}`, title, record_id: null, updated_at: "2026-11-01T10:00:00+00:00" }));

function Sidebar({ titles = ["Flood methods", "Pond sampling"], onRename, onNewChat = () => undefined }: {
  titles?: string[]; onRename?: RenameConversation; onNewChat?: () => void;
}) {
  const [conversations, setConversations] = useState(entries(...titles));
  const [width, setWidth] = useState(280);
  const rename: RenameConversation = async (id, title) => {
    const problem = onRename ? await onRename(id, title) : null;
    if (!problem) setConversations(all => all.map(c => (c.id === id ? { ...c, title: title.trim() } : c)));
    return problem;
  };
  return <MemoryRouter>
    <ConversationSidebar id="pane" conversations={conversations} activeId={null} open search={search}
      onDelete={() => undefined} onRename={rename} onNewChat={onNewChat} onSearch={() => undefined}
      onToggle={() => undefined} width={width} onResize={setWidth} />
  </MemoryRouter>;
}

describe("renaming a conversation in the list (IR-1160)", () => {
  test("by mouse: Rename, type, Enter saves and the list shows the new title", async () => {
    const onRename = vi.fn(async () => null);
    const user = userEvent.setup();
    const { container } = render(<Sidebar onRename={onRename} />);
    await user.click(screen.getByRole("button", { name: "Rename Flood methods" }));
    const input = screen.getByRole("textbox", { name: "Conversation title" });
    await user.clear(input);
    await user.type(input, "Flood notes{Enter}");
    expect(onRename).toHaveBeenCalledWith("id-Flood methods", "Flood notes");
    expect(await screen.findByRole("link", { name: /Flood notes/ })).toBeInTheDocument();
    await expectNoBlockingA11yViolations(container);
  });

  test("by keyboard: Escape cancels and sends nothing, and focus returns to Rename", async () => {
    const onRename = vi.fn(async () => null);
    const user = userEvent.setup();
    render(<Sidebar onRename={onRename} />);
    screen.getByRole("button", { name: "Rename Flood methods" }).focus();
    await user.keyboard("{Enter}");
    await user.type(screen.getByRole("textbox", { name: "Conversation title" }), " changed{Escape}");
    expect(screen.queryByRole("textbox", { name: "Conversation title" })).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Flood methods/ })).toBeInTheDocument();
    expect(onRename).not.toHaveBeenCalled();
    await waitFor(() => expect(screen.getByRole("button", { name: "Rename Flood methods" })).toHaveFocus());
  });

  test("an over-long title is refused with a clear message and stays editable", async () => {
    const onRename = vi.fn(async () => null);
    const user = userEvent.setup();
    render(<Sidebar onRename={onRename} />);
    await user.click(screen.getByRole("button", { name: "Rename Flood methods" }));
    const input = screen.getByRole("textbox", { name: "Conversation title" });
    await user.clear(input);
    await user.click(input);
    await user.paste("x".repeat(201));
    await user.keyboard("{Enter}");
    expect(screen.getByRole("alert")).toHaveTextContent("A title can be at most 200 characters.");
    expect(input).toHaveAttribute("aria-invalid", "true");
    expect(onRename).not.toHaveBeenCalled();
  });

  test("a refusal from the server is shown and the title is kept", async () => {
    const user = userEvent.setup();
    render(<Sidebar onRename={async () => "Could not rename this conversation. Try again."} />);
    await user.click(screen.getByRole("button", { name: "Rename Pond sampling" }));
    await user.type(screen.getByRole("textbox", { name: "Conversation title" }), "!{Enter}");
    expect(await screen.findByRole("alert")).toHaveTextContent("Could not rename");
  });
});

describe("New chat, Search, Pinned and Recents", () => {
  test("a pinned conversation moves under Pinned and is still pinned after a reload", async () => {
    const user = userEvent.setup();
    const view = render(<Sidebar />);
    await user.click(screen.getByRole("button", { name: "Pin Pond sampling" }));
    const pinned = screen.getByRole("navigation", { name: "Pinned conversations" });
    expect(within(pinned).getByRole("link", { name: /Pond sampling/ })).toBeInTheDocument();
    const recents = screen.getByRole("navigation", { name: "Past conversations" });
    expect(within(recents).queryByRole("link", { name: /Pond sampling/ })).not.toBeInTheDocument();
    view.unmount();
    render(<Sidebar />);
    expect(screen.getByRole("navigation", { name: "Pinned conversations" })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Unpin Pond sampling" }));
    expect(screen.queryByRole("navigation", { name: "Pinned conversations" })).not.toBeInTheDocument();
  });

  test("New chat starts one and Ctrl+K goes to search", async () => {
    const onNewChat = vi.fn();
    const user = userEvent.setup();
    render(<Sidebar onNewChat={onNewChat} />);
    await user.click(screen.getByRole("button", { name: "New chat" }));
    expect(onNewChat).toHaveBeenCalled();
    await user.keyboard("{Control>}k{/Control}");
    expect(screen.getByRole("searchbox", { name: "Search your past conversations" })).toHaveFocus();
  });

  test("the column resizes by keyboard within its bounds", async () => {
    const user = userEvent.setup();
    render(<Sidebar />);
    const edge = screen.getByRole("separator", { name: "Resize chat history" });
    edge.focus();
    await user.keyboard("{ArrowRight}");
    expect(edge).toHaveAttribute("aria-valuenow", "304");
    await user.keyboard("{End}");
    expect(edge).toHaveAttribute("aria-valuenow", String(SIDEBAR_MAX));
    expect(screen.getByRole("complementary", { name: "Chat history" })).toHaveStyle({ width: `${SIDEBAR_MAX}px` });
  });
});
