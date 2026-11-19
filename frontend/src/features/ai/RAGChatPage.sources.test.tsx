/**
 * Ask IRIS's Sources panel (IR-1237): a citation opens the passage it cites,
 * beside the chat on a wide page, over it on a tablet and as a sheet on a phone.
 *
 * Replays the recorded conversation (its answer cites two passages in two
 * papers); requests are answered at the axios adapter, and the page's width is
 * whatever the stubbed `ResizeObserver` reports, as `RAGChatPage.pane.test.tsx` does.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { AxiosAdapter, InternalAxiosRequestConfig } from "axios";
import { Route, Routes } from "react-router-dom";
import { renderScreen, screen, userEvent, waitFor, within } from "@/test/render";
import { expectNoBlockingA11yViolations } from "@/test/axe";
import { apiClient } from "@/api/client";
import recorded from "@/test/fixtures/runtimeReader.recorded.json";
import RAGChatPage from "./RAGChatPage";

const { conversation } = recorded;
let originalAdapter: InternalAxiosRequestConfig["adapter"];

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

async function openAnswer() {
  const view = renderScreen(
    <Routes><Route path="/ai/conversations/:conversationId" element={<RAGChatPage />} /></Routes>,
    { route: `/ai/conversations/${conversation.id}` },
  );
  // The first render in a run is slow under a loaded CI worker.
  await screen.findByRole("button", { name: "Source 2: Pond sampling, page 5" }, { timeout: 5000 });
  return view;
}

beforeEach(() => {
  localStorage.clear();
  Element.prototype.scrollIntoView = vi.fn();
  originalAdapter = apiClient.defaults.adapter;
  const adapter: AxiosAdapter = async (config) => {
    const url = config.url ?? "";
    let data: unknown;
    if (url === "/ai/conversations/") data = [];
    else if (url === "/ai/runtime/conversations") data = { protocol: "runs-reader-1", next: null, conversations: [] };
    else if (url === `/ai/runtime/conversations/${conversation.id}`) data = conversation;
    else if (url === "/records/1/") data = { id: 1, title: "Flood sensors", abstract: "", authors: [{ name: "A. Reyes" }], publication_year: 2024 };
    else if (url === "/records/2/") data = { id: 2, title: "Pond sampling", abstract: "", authors: [{ name: "B. Cruz" }], publication_year: 2022 };
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

describe("on a wide page", () => {
  beforeEach(() => pageAt(1280));

  it("starts with the panel closed, and the header toggle says it shows sources", async () => {
    await openAnswer();

    expect(screen.queryByRole("complementary", { name: "Sources" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Show sources" })).toHaveAttribute("aria-expanded", "false");
  });

  it("opens beside the chat at the passage a chip cites, with that chip pressed", async () => {
    const user = userEvent.setup();
    const { container } = await openAnswer();

    const chip = screen.getByRole("button", { name: "Source 2: Pond sampling, page 5" });
    await user.click(chip);

    const panel = screen.getByRole("complementary", { name: "Sources" });
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(chip).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByRole("button", { name: "Source 1: Flood sensors, page 3" })).toHaveAttribute("aria-pressed", "false");
    expect(within(panel).getByRole("listitem", { name: /^Source 2/ })).toHaveAttribute("aria-current", "true");
    expect(within(panel).getByRole("listitem", { name: /^Source 1/ })).not.toHaveAttribute("aria-current");
    expect(Element.prototype.scrollIntoView).toHaveBeenCalled();
    expect(within(panel).getByText("pond water sampled weekly for turbidity")).toBeInTheDocument();
    expect(within(panel).getByRole("link", { name: "Open at page 5 in Pond sampling" })).toHaveAttribute("href", "/records/2?page=5");
    expect(within(panel).getByRole("link", { name: "Open at page 3 in Flood sensors" })).toHaveAttribute("href", "/records/1?page=3");
    expect(screen.getByRole("button", { name: "Hide sources" })).toHaveAttribute("aria-expanded", "true");
    await expectNoBlockingA11yViolations(container);
  });

  it("moves the highlight to another chip", async () => {
    const user = userEvent.setup();
    await openAnswer();
    await user.click(screen.getByRole("button", { name: /^Source 2:/ }));
    await user.click(screen.getByRole("button", { name: /^Source 1:/ }));

    expect(screen.getByRole("button", { name: /^Source 1:/ })).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByRole("button", { name: /^Source 2:/ })).toHaveAttribute("aria-pressed", "false");
    expect(screen.getByRole("listitem", { name: /^Source 1/ })).toHaveAttribute("aria-current", "true");
  });

  it("opens from the count with nothing highlighted, and the count matches the citations", async () => {
    const user = userEvent.setup();
    await openAnswer();

    await user.click(screen.getByRole("button", { name: "2 passages from 2 papers" }));

    const panel = screen.getByRole("complementary", { name: "Sources" });
    expect(within(panel).getAllByRole("listitem")).toHaveLength(2);
    expect(within(panel).queryByRole("listitem", { current: true })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: /^Source 2:/ })).toHaveAttribute("aria-pressed", "false");
  });

  it("opens and closes from the header toggle", async () => {
    const user = userEvent.setup();
    await openAnswer();

    await user.click(screen.getByRole("button", { name: "Show sources" }));
    const panel = screen.getByRole("complementary", { name: "Sources" });
    expect(within(panel).getAllByRole("listitem")).toHaveLength(2);
    expect(screen.getByRole("button", { name: "Hide sources" })).toHaveAttribute("aria-controls", panel.id);

    await user.click(screen.getByRole("button", { name: "Hide sources" }));
    expect(screen.queryByRole("complementary", { name: "Sources" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Show sources" })).toHaveAttribute("aria-expanded", "false");
  });

  it("closes with Escape and with its X", async () => {
    const user = userEvent.setup();
    await openAnswer();
    await user.click(screen.getByRole("button", { name: /^Source 1:/ }));
    await user.keyboard("{Escape}");
    await waitFor(() => expect(screen.queryByRole("complementary", { name: "Sources" })).not.toBeInTheDocument());

    await user.click(screen.getByRole("button", { name: /^Source 1:/ }));
    await user.click(screen.getByRole("button", { name: "Close sources" }));
    expect(screen.queryByRole("complementary", { name: "Sources" })).not.toBeInTheDocument();
  });

  it("puts Edit and Copy under the question, and Copy and Ask again under the answer", async () => {
    await openAnswer();

    expect(screen.getByRole("button", { name: "Edit" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Copy question" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Copy answer" })).toBeInTheDocument();
    expect(screen.getAllByRole("button", { name: "Ask again" })).toHaveLength(1);
  });
});

describe("on a tablet", () => {
  it("opens over the chat as a dialog", async () => {
    pageAt(768);
    const user = userEvent.setup();
    await openAnswer();

    await user.click(screen.getByRole("button", { name: /^Source 2:/ }));

    const dialog = screen.getByRole("dialog", { name: "Sources" });
    expect(dialog).toHaveAttribute("data-placement", "end");
    expect(within(dialog).getByRole("listitem", { name: /^Source 2/ })).toHaveAttribute("aria-current", "true");
    await user.keyboard("{Escape}");
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });
});

describe("on a phone", () => {
  it("opens as a bottom sheet that its X closes", async () => {
    pageAt(360);
    const user = userEvent.setup();
    const { container } = await openAnswer();

    await user.click(screen.getByRole("button", { name: /^Source 1:/ }));

    const sheet = screen.getByRole("dialog", { name: "Sources" });
    expect(sheet).toHaveAttribute("data-placement", "bottom");
    expect(within(sheet).getByRole("link", { name: "Open at page 3 in Flood sensors" })).toBeInTheDocument();
    await expectNoBlockingA11yViolations(container);

    await user.click(within(sheet).getByRole("button", { name: "Close sources" }));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });
});
