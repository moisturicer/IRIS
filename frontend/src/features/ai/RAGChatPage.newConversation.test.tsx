/**
 * One New conversation control on screen at a time, and Ask IRIS saying
 * "conversation" everywhere (IR-1234).
 *
 * The page is rendered through its routes, with requests answered at the axios
 * adapter, and its width is whatever the stubbed `ResizeObserver` reports, as
 * `PaperViewPage.test.tsx` does for the Paper layouts.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { AxiosAdapter, InternalAxiosRequestConfig } from "axios";
import { Route, Routes, useLocation } from "react-router-dom";
import { renderScreen, screen, userEvent, waitFor, within } from "@/test/render";
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


const CONVERSATION = "/ai/conversations/11111111-1111-1111-1111-111111111111";
const controls = () => [
  ...screen.queryAllByRole("button", { name: "New conversation" }),
  ...screen.queryAllByRole("link", { name: "New conversation" }),
];

describe("on a page wider than a phone", () => {
  beforeEach(() => pageAt(1280));

  it.each([["an empty page", "/ai"], ["an open conversation", CONVERSATION]])("has one control with the pane open, on %s", async (_, at) => {
    renderAsk(at);
    await flood();
    expect(controls()).toHaveLength(1);
  });

  it("has one control with the pane collapsed to its strip", async () => {
    const user = userEvent.setup();
    renderAsk(CONVERSATION);
    await flood();
    await user.click(screen.getByRole("button", { name: "Hide history" }));
    expect(controls()).toHaveLength(1);
  });

  it("puts the cursor in the question box after New conversation, also from an empty page", async () => {
    const user = userEvent.setup();
    renderAsk(CONVERSATION);
    await flood();
    await user.click(controls()[0]);
    expect(address).toBe("/ai");
    await waitFor(() => expect(screen.getByRole("textbox", { name: /question|ask/i })).toHaveFocus());

    screen.getByRole("link", { name: /Flood methods/ }).focus();
    await user.click(controls()[0]);
    expect(screen.getByRole("textbox", { name: /question|ask/i })).toHaveFocus();
  });

  it("titles an empty page Ask IRIS, once", async () => {
    renderAsk();
    await flood();
    expect(screen.getByRole("heading", { level: 1, name: "Ask IRIS" })).toBeInTheDocument();
    expect(screen.getAllByText("Ask IRIS")).toHaveLength(1);
  });

  it("says conversation, never chat, in the pane", async () => {
    const { container } = renderAsk();
    await flood();
    expect(screen.getByRole("complementary", { name: "History" })).toBeInTheDocument();
    expect(container.textContent).not.toMatch(/\bchat\b/i);
  });
});

describe("on a phone", () => {
  beforeEach(() => pageAt(360));

  it("has the header icon while a conversation is open, and none on the empty page", async () => {
    const empty = renderAsk();
    await screen.findByRole("button", { name: "Show history" });
    expect(controls()).toHaveLength(0);
    empty.unmount();

    renderAsk(CONVERSATION);
    await screen.findByRole("button", { name: "Show history" });
    expect(controls()).toHaveLength(1);
  });

  it("has only the drawer's button while the drawer is open", async () => {
    const user = userEvent.setup();
    renderAsk(CONVERSATION);
    await user.click(await screen.findByRole("button", { name: "Show history" }));
    const dialog = await screen.findByRole("dialog", { name: "History" });
    expect(controls()).toHaveLength(1);
    expect(within(dialog).getByRole("button", { name: "New conversation" })).toBeInTheDocument();
  });

  it("starts a conversation from the header icon, with focus in the question box", async () => {
    const user = userEvent.setup();
    renderAsk(CONVERSATION);
    await screen.findByRole("button", { name: "Show history" });
    await user.click(controls()[0]);
    expect(address).toBe("/ai");
    await waitFor(() => expect(screen.getByRole("textbox", { name: /question|ask/i })).toHaveFocus());
  });
});
