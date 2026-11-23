/**
 * New conversation, Search, Pinned and Recents, rename in place (IR-1160) and a resizable column.
 *
 * Each row is one line with a ⋯ menu for Pin, Rename and Delete (IR-1253), so hovering
 * never reflows its title. Changed deliberately by IR-1253: the actions were three
 * buttons (`Rename <title>`, `Pin <title>`); they are now items in that menu.
 */
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
  text: "", onText: () => undefined, query: "", state: "ready", onRetry: () => undefined, hasMore: false, loadingMore: false, onMore: () => undefined,
};

const entries = (...titles: string[]): ReaderConversationSummary[] =>
  titles.map(title => ({ id: `id-${title}`, title, record_id: null, updated_at: "2026-11-01T10:00:00+00:00" }));

function Sidebar({ titles = ["Flood methods", "Pond sampling"], onRename, onDelete = () => undefined, onNewConversation = () => undefined }: {
  titles?: string[]; onRename?: RenameConversation; onDelete?: (id: string) => void; onNewConversation?: () => void;
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
      onDelete={onDelete} onRename={rename} onNewConversation={onNewConversation} onSearch={() => undefined}
      onToggle={() => undefined} width={width} onResize={setWidth} />
  </MemoryRouter>;
}

type User = ReturnType<typeof userEvent.setup>;

/** Open a row's ⋯ menu and choose an item (IR-1253). */
async function choose(user: User, title: string, item: string) {
  await user.click(screen.getByRole("button", { name: `Actions for ${title}` }));
  await user.click(within(screen.getByRole("menu", { name: `Actions for ${title}` })).getByRole("menuitem", { name: item }));
}

describe("a conversation's row (IR-1253)", () => {
  test("has one ⋯ menu, not three buttons, holding Pin, Rename and Delete", async () => {
    const user = userEvent.setup();
    const { container } = render(<Sidebar />);
    const row = screen.getByRole("link", { name: /Flood methods/ }).closest("li")!;

    expect(within(row).getAllByRole("button").map(b => b.getAttribute("aria-label"))).toEqual(["Actions for Flood methods"]);
    await user.click(within(row).getByRole("button", { name: "Actions for Flood methods" }));
    const menu = screen.getByRole("menu", { name: "Actions for Flood methods" });
    expect(within(menu).getAllByRole("menuitem").map(i => i.textContent)).toEqual(["Pin", "Rename", "Delete"]);
    await expectNoBlockingA11yViolations(container);
  });

  // The Full Text Rule's seventh cut (DESIGN.md): a cut title is still whole for
  // everyone. jsdom draws nothing, so the cut is stated by its widths.
  test("shows a cut title whole on keyboard focus, and reads it whole, but no tip for one that fits", async () => {
    const long = "A conversation about rainwater harvesting in urban centres across the Visayas region";
    vi.spyOn(HTMLElement.prototype, "scrollWidth", "get")
      .mockImplementation(function (this: HTMLElement) { return this.textContent === long ? 400 : 100; });
    vi.spyOn(HTMLElement.prototype, "clientWidth", "get").mockReturnValue(200);
    const user = userEvent.setup();
    render(<Sidebar titles={[long, "Short one"]} />);

    const longLink = screen.getByRole("link", { name: new RegExp(long) });
    expect(longLink).not.toHaveAttribute("title");
    longLink.focus();
    expect(await screen.findByRole("tooltip")).toHaveTextContent(long);

    await user.tab(); // its ⋯ menu
    await user.tab(); // the short title's link
    expect(screen.getByRole("link", { name: /Short one/ })).toHaveFocus();
    expect(screen.queryByRole("tooltip")).not.toBeInTheDocument();
  });

  test("Delete from the menu deletes that conversation", async () => {
    const onDelete = vi.fn();
    const user = userEvent.setup();
    render(<Sidebar onDelete={onDelete} />);
    await choose(user, "Pond sampling", "Delete");
    expect(onDelete).toHaveBeenCalledWith("id-Pond sampling");
  });
});

describe("renaming a conversation in the list (IR-1160)", () => {
  test("by mouse: Rename, type, Enter saves and the list shows the new title", async () => {
    const onRename = vi.fn(async () => null);
    const user = userEvent.setup();
    const { container } = render(<Sidebar onRename={onRename} />);
    await choose(user, "Flood methods", "Rename");
    const input = screen.getByRole("textbox", { name: "Conversation title" });
    await user.clear(input);
    await user.type(input, "Flood notes{Enter}");
    expect(onRename).toHaveBeenCalledWith("id-Flood methods", "Flood notes");
    expect(await screen.findByRole("link", { name: /Flood notes/ })).toBeInTheDocument();
    await expectNoBlockingA11yViolations(container);
  });

  test("by keyboard: Escape cancels and sends nothing, and focus returns to the row's ⋯ menu", async () => {
    const onRename = vi.fn(async () => null);
    const user = userEvent.setup();
    render(<Sidebar onRename={onRename} />);
    screen.getByRole("button", { name: "Actions for Flood methods" }).focus();
    await user.keyboard("{Enter}");
    // The menu opens on its first item, Pin; Rename is next.
    await waitFor(() => expect(screen.getByRole("menuitem", { name: "Pin" })).toHaveFocus());
    await user.keyboard("{ArrowDown}{Enter}");
    await user.type(screen.getByRole("textbox", { name: "Conversation title" }), " changed{Escape}");
    expect(screen.queryByRole("textbox", { name: "Conversation title" })).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Flood methods/ })).toBeInTheDocument();
    expect(onRename).not.toHaveBeenCalled();
    await waitFor(() => expect(screen.getByRole("button", { name: "Actions for Flood methods" })).toHaveFocus());
  });

  test("an over-long title is refused with a clear message and stays editable", async () => {
    const onRename = vi.fn(async () => null);
    const user = userEvent.setup();
    render(<Sidebar onRename={onRename} />);
    await choose(user, "Flood methods", "Rename");
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
    await choose(user, "Pond sampling", "Rename");
    await user.type(screen.getByRole("textbox", { name: "Conversation title" }), "!{Enter}");
    expect(await screen.findByRole("alert")).toHaveTextContent("Could not rename");
  });
});

describe("New conversation, Search, Pinned and Recents", () => {
  test("a pinned conversation moves under Pinned and is still pinned after a reload", async () => {
    const user = userEvent.setup();
    const view = render(<Sidebar />);
    await choose(user, "Pond sampling", "Pin");
    const pinned = screen.getByRole("navigation", { name: "Pinned conversations" });
    expect(within(pinned).getByRole("link", { name: /Pond sampling/ })).toBeInTheDocument();
    const recents = screen.getByRole("navigation", { name: "Past conversations" });
    expect(within(recents).queryByRole("link", { name: /Pond sampling/ })).not.toBeInTheDocument();
    view.unmount();
    render(<Sidebar />);
    expect(screen.getByRole("navigation", { name: "Pinned conversations" })).toBeInTheDocument();
    await choose(user, "Pond sampling", "Unpin");
    expect(screen.queryByRole("navigation", { name: "Pinned conversations" })).not.toBeInTheDocument();
  });

  test("New conversation starts one and Ctrl+K goes to search", async () => {
    const onNewConversation = vi.fn();
    const user = userEvent.setup();
    render(<Sidebar onNewConversation={onNewConversation} />);
    await user.click(screen.getByRole("button", { name: "New conversation" }));
    expect(onNewConversation).toHaveBeenCalled();
    await user.keyboard("{Control>}k{/Control}");
    expect(screen.getByRole("searchbox", { name: "Search your past conversations" })).toHaveFocus();
  });

  // IR-1257: on the pane's stone-50 the box vanished until hovered.
  test("the search box has a fill and an outline at rest, and shows typing in the outline only", () => {
    render(<Sidebar />);
    const box = screen.getByRole("searchbox", { name: "Search your past conversations" }).closest("label") as HTMLElement;
    // The field outline every IRIS search box has, and its focus border and ring.
    expect(box).toHaveClass("bg-stone-100", "border", "border-field", "focus-within:border-brand", "focus-within:ring-2");
    // Like every other search box in IRIS, hovering and typing never change the fill.
    expect(box.className).not.toMatch(/(^|\s)hover:/);
    expect(box.className).not.toMatch(/(^|\s)focus-within:bg-/);
    // Conversation rows keep their own style: no fill at rest.
    expect(screen.getByRole("link", { name: /Pond sampling/ }).className).not.toMatch(/(^|\s)bg-/);
  });

  test("the column resizes by keyboard within its bounds", async () => {
    const user = userEvent.setup();
    render(<Sidebar />);
    const edge = screen.getByRole("separator", { name: "Resize conversations" });
    edge.focus();
    // The pane is on the right (IR-1306): its edge faces left, so ArrowLeft widens it.
    await user.keyboard("{ArrowLeft}");
    expect(edge).toHaveAttribute("aria-valuenow", "304");
    await user.keyboard("{End}");
    expect(edge).toHaveAttribute("aria-valuenow", String(SIDEBAR_MAX));
    expect(screen.getByRole("complementary", { name: "Conversations" })).toHaveStyle({ width: `${SIDEBAR_MAX}px` });
  });
});
