/**
 * The conversations pane on the Ask IRIS page (IR-1233): one toggle that opens
 * and closes it in place, a narrow strip while it is closed, and a dialog over
 * the chat on a phone.
 *
 * The page is rendered through its routes, with requests answered at the axios
 * adapter, and its width is whatever the stubbed `ResizeObserver` reports, as
 * `PaperViewPage.test.tsx` does for the Paper layouts.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { AxiosAdapter, InternalAxiosRequestConfig } from "axios";
import { Route, Routes, useLocation } from "react-router-dom";
import { renderScreen, screen, userEvent, within } from "@/test/render";
import { expectNoBlockingA11yViolations } from "@/test/axe";
import { apiClient } from "@/api/client";
import RAGChatPage from "./RAGChatPage";

let originalAdapter: InternalAxiosRequestConfig["adapter"];
let address = "";

const LIST = {
  protocol: "runs-reader-1", next: null,
  conversations: [
    { id: "11111111-1111-1111-1111-111111111111", title: "Flood methods", record_id: null, updated_at: "2026-11-01T10:00:00+00:00" },
    { id: "22222222-2222-2222-2222-222222222222", title: "Pond sampling", record_id: null, updated_at: "2026-11-01T09:00:00+00:00" },
  ],
};

/** Reports `width` to whatever observes an element, as the browser would. */
function pageAt(width: number) {
  vi.stubGlobal("ResizeObserver", class {
    constructor(private readonly callback: ResizeObserverCallback) {}
    observe(target: Element) {
      this.callback([{ target, contentRect: { width } } as unknown as ResizeObserverEntry], this as unknown as ResizeObserver);
    }
    unobserve() {}
    disconnect() {}
  });
}

function Address() {
  address = useLocation().pathname;
  return null;
}

function renderAsk(at = "/ai") {
  return renderScreen(
    <>
      <Routes>
        <Route path="/ai" element={<RAGChatPage />} />
        <Route path="/ai/conversations/:conversationId" element={<RAGChatPage />} />
      </Routes>
      <Address />
    </>,
    { route: at },
  );
}

const flood = () => screen.findByRole("link", { name: /Flood methods/ });

beforeEach(() => {
  localStorage.clear();
  Element.prototype.scrollIntoView = vi.fn();
  originalAdapter = apiClient.defaults.adapter;
  const adapter: AxiosAdapter = async (config) => {
    const url = config.url ?? "";
    let data: unknown;
    if (url === "/ai/conversations/") data = [];
    else if (url === "/ai/runtime/conversations") data = LIST;
    else throw new Error(`unexpected request ${config.method} ${url}`);
    return { data, status: 200, statusText: "", headers: {}, config };
  };
  apiClient.defaults.adapter = adapter;
});

afterEach(() => {
  apiClient.defaults.adapter = originalAdapter;
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("on a page wider than a phone", () => {
  beforeEach(() => pageAt(1280));

  it("shows the list beside the chat, with one toggle that says it hides it", async () => {
    const { container } = renderAsk();
    await flood();
    const hide = screen.getByRole("button", { name: "Hide history" });
    expect(hide).toHaveAttribute("aria-expanded", "true");
    expect(hide).toHaveAttribute("aria-controls", screen.getByRole("complementary", { name: "History" }).id);
    // The chat's own header carries no second toggle on these widths.
    expect(screen.getAllByRole("button", { name: /history$/ })).toHaveLength(1);
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    await expectNoBlockingA11yViolations(container);
  });

  it("hides the list in place and leaves focus on the toggle, now Show history", async () => {
    const user = userEvent.setup();
    const { container } = renderAsk();
    await flood();
    await user.click(screen.getByRole("button", { name: "Hide history" }));

    expect(screen.queryByRole("link", { name: /Flood methods/ })).not.toBeInTheDocument();
    const show = screen.getByRole("button", { name: "Show history" });
    expect(show).toHaveAttribute("aria-expanded", "false");
    expect(show).toHaveFocus();
    await expectNoBlockingA11yViolations(container);

    await user.click(show);
    expect(await flood()).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Hide history" })).toHaveFocus();
  });

  it("works from the keyboard", async () => {
    const user = userEvent.setup();
    renderAsk();
    await flood();
    screen.getByRole("button", { name: "Hide history" }).focus();
    await user.keyboard("{Enter}");
    expect(screen.getByRole("button", { name: "Show history" })).toHaveFocus();
    await user.keyboard(" ");
    expect(screen.getByRole("button", { name: "Hide history" })).toHaveFocus();
  });

  it("keeps a New conversation icon in the strip, and it starts one", async () => {
    const user = userEvent.setup();
    renderAsk("/ai/conversations/11111111-1111-1111-1111-111111111111");
    await flood();
    await user.click(screen.getByRole("button", { name: "Hide history" }));
    await user.click(screen.getByRole("button", { name: "New conversation" }));
    expect(address).toBe("/ai");
  });

  it("opens the pane from the strip's Search, with focus in the search box", async () => {
    const user = userEvent.setup();
    renderAsk();
    await flood();
    await user.click(screen.getByRole("button", { name: "Hide history" }));
    expect(screen.queryByRole("searchbox")).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Search conversations" }));
    expect(screen.getByRole("searchbox", { name: "Search your past conversations" })).toHaveFocus();
    expect(screen.getByRole("button", { name: "Hide history" })).toHaveAttribute("aria-expanded", "true");
    expect(screen.queryByRole("button", { name: "Search conversations" })).not.toBeInTheDocument();
  });

  it("opens the pane on Ctrl+K while it is closed, and still just focuses search while it is open", async () => {
    const user = userEvent.setup();
    renderAsk();
    await flood();
    await user.keyboard("{Control>}k{/Control}");
    expect(screen.getByRole("searchbox", { name: "Search your past conversations" })).toHaveFocus();

    await user.click(screen.getByRole("button", { name: "Hide history" }));
    expect(screen.queryByRole("searchbox")).not.toBeInTheDocument();
    await user.keyboard("{Control>}k{/Control}");
    expect(screen.getByRole("searchbox", { name: "Search your past conversations" })).toHaveFocus();
    expect(screen.getByRole("button", { name: "Hide history" })).toHaveAttribute("aria-expanded", "true");
  });

  it("remembers a closed pane after a reload", async () => {
    const user = userEvent.setup();
    const first = renderAsk();
    await flood();
    await user.click(screen.getByRole("button", { name: "Hide history" }));
    first.unmount();

    renderAsk();
    expect(await screen.findByRole("button", { name: "Show history" })).toHaveAttribute("aria-expanded", "false");
    expect(screen.queryByRole("link", { name: /Flood methods/ })).not.toBeInTheDocument();
  });

  it("starts open when the browser will not give storage", async () => {
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => { throw new Error("blocked"); });
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => { throw new Error("blocked"); });
    const user = userEvent.setup();
    renderAsk();
    await flood();
    // Choosing still works for this visit.
    await user.click(screen.getByRole("button", { name: "Hide history" }));
    expect(screen.getByRole("button", { name: "Show history" })).toBeInTheDocument();
  });
});

describe("on a tablet", () => {
  it("pushes the chat over rather than overlaying it", async () => {
    pageAt(768);
    renderAsk();
    await flood();
    expect(screen.getByRole("button", { name: "Hide history" })).toHaveAttribute("aria-expanded", "true");
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });
});

describe("on a phone", () => {
  beforeEach(() => pageAt(360));

  it("starts with the chat alone, and a Show history button in the chat header", async () => {
    const { container } = renderAsk();
    const show = await screen.findByRole("button", { name: "Show history" });
    expect(show).toHaveAttribute("aria-expanded", "false");
    expect(show).toHaveAttribute("aria-haspopup", "dialog");
    expect(screen.queryByRole("link", { name: /Flood methods/ })).not.toBeInTheDocument();
    expect(screen.queryByRole("complementary")).not.toBeInTheDocument();
    await expectNoBlockingA11yViolations(container);
  });

  it("opens the list as a dialog over the chat; Escape closes it and focus returns to the opener", async () => {
    const user = userEvent.setup();
    renderAsk();
    const show = await screen.findByRole("button", { name: "Show history" });
    await user.click(show);

    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByRole("link", { name: /Flood methods/ })).toBeInTheDocument();
    await user.keyboard("{Escape}");
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Show history" })).toHaveFocus();
  });

  it("closes with its X, and focus returns to the opener", async () => {
    const user = userEvent.setup();
    renderAsk();
    await user.click(await screen.findByRole("button", { name: "Show history" }));
    await user.click(await screen.findByRole("button", { name: "Close history" }));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Show history" })).toHaveFocus();
  });

  it("opens the dialog on Ctrl+K, with focus in the search box", async () => {
    const user = userEvent.setup();
    renderAsk();
    await screen.findByRole("button", { name: "Show history" });
    await user.keyboard("{Control>}k{/Control}");
    expect(await screen.findByRole("dialog")).toBeInTheDocument();
    expect(screen.getByRole("searchbox", { name: "Search your past conversations" })).toHaveFocus();
  });

  it("does not use the saved choice from a wider screen", async () => {
    localStorage.setItem("iris-ask-pane", "open");
    renderAsk();
    await screen.findByRole("button", { name: "Show history" });
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });
});
