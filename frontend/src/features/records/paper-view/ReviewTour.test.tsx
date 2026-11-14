/**
 * The Review workspace's guided tour (IR-997).
 *
 * Tested through the rendered workspace, as a reviewer meets it: the first-visit
 * offer, the steps, Next / Previous / Skip, starting again, and keyboard focus.
 * jsdom has no layout, so where a step *sits* on the page is not asserted here;
 * which steps exist, what they say and what they leave untouched is.
 */
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { Capability } from "@/features/records/capabilities";
import { expectNoBlockingA11yViolations } from "@/test/axe";
import { renderScreen, screen, within } from "@/test/render";
import type { RecordDetail } from "@/types/records";

import { ReviewWorkspace } from "./ReviewWorkspace";

const api = vi.hoisted(() => ({
  tracker: vi.fn(() => new Promise(() => {})),
  documentRequestSlots: vi.fn(() => new Promise(() => {})),
  reviewComments: vi.fn(() => new Promise(() => {})),
  responseLetters: vi.fn(() => new Promise(() => {})),
}));
vi.mock("@/api/records", () => ({ recordsApi: api }));

const record = (versions: number) => ({
  id: 7,
  title: "Flood-Risk Mapping",
  can_request_document: [],
  current_holders: [],
  files: [],
  keywords: [],
  abstract_file: null,
  my_seats: [{ id: 1, party: "itso", state: "in_review", assignment: 3, verdict_label: null, state_label: "Reviewing" }],
  versions: Array.from({ length: versions }, (_, i) => ({ number: i + 1 })),
  review_claim: null,
  routing: { send_to_rdco: false, send_to_rdco_blocked: null, route_as: null, targets: [] },
}) as unknown as RecordDetail;

/** Makes the workspace's container `width` px wide (the layout reads it through a ResizeObserver). */
function widthOf(width: number) {
  vi.stubGlobal("ResizeObserver", class {
    constructor(private readonly callback: ResizeObserverCallback) {}
    observe(target: Element) {
      this.callback([{ target, contentRect: { width, height: 600 },
        borderBoxSize: [{ blockSize: 600, inlineSize: width }] } as unknown as ResizeObserverEntry], this as unknown as ResizeObserver);
    }
    unobserve() {}
    disconnect() {}
  });
}

function openWorkspace({ versions = 2, reader = true, caps = ["comment_review"] as Capability[] } = {}) {
  return renderScreen(
    <ReviewWorkspace record={record(versions)} can={new Set(caps)} reader={reader ? <div>The paper</div> : null}
      timelineVersion={0} onChanged={() => {}} documents={null} documentsOpen={false} onDocuments={() => {}} />,
  );
}

const tourDialog = () => screen.queryByRole("dialog", { name: "Review workspace tour" });
const progress = () => within(screen.getByRole("dialog", { name: "Review workspace tour" })).getByText(/^Step \d+ of \d+$/).textContent;
const stepTitle = () => within(screen.getByRole("dialog", { name: "Review workspace tour" })).getByRole("heading").textContent;

beforeEach(() => {
  localStorage.clear();
});
afterEach(() => {
  vi.unstubAllGlobals();
});

describe("being offered the tour (IR-997)", () => {
  it("offers it to a first-time reviewer without starting it", () => {
    openWorkspace();
    expect(screen.getByRole("button", { name: "Start tour" })).toBeInTheDocument();
    expect(tourDialog()).toBeNull();
  });

  it("stops offering it once dismissed, across visits, and keeps Take a tour", async () => {
    const user = userEvent.setup();
    const first = openWorkspace();
    await user.click(screen.getByRole("button", { name: "Not now" }));
    expect(screen.queryByRole("button", { name: "Start tour" })).toBeNull();

    first.unmount();
    openWorkspace();
    expect(screen.queryByRole("button", { name: "Start tour" })).toBeNull();
    expect(screen.getByRole("button", { name: "Take a tour" })).toBeInTheDocument();
  });

  it("still opens when the browser will not keep the choice", async () => {
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => { throw new Error("blocked"); });
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => { throw new Error("blocked"); });
    const user = userEvent.setup();
    openWorkspace();
    await user.click(screen.getByRole("button", { name: "Start tour" }));
    expect(tourDialog()).toBeInTheDocument();
  });
});

describe("walking through the tour (IR-997)", () => {
  it("shows one step at a time, with progress, Next and Previous", async () => {
    const user = userEvent.setup();
    openWorkspace();
    await user.click(screen.getByRole("button", { name: "Start tour" }));

    expect(progress()).toBe("Step 1 of 3");
    expect(stepTitle()).toBe("The paper");
    expect(screen.getByRole("button", { name: "Previous" })).toBeDisabled();

    await user.click(screen.getByRole("button", { name: "Next" }));
    expect(progress()).toBe("Step 2 of 3");
    expect(stepTitle()).toBe("Review pane sections");

    await user.click(screen.getByRole("button", { name: "Previous" }));
    expect(progress()).toBe("Step 1 of 3");
  });

  it("names only the tabs this workspace has", async () => {
    const user = userEvent.setup();
    openWorkspace({ versions: 1 });
    await user.click(screen.getByRole("button", { name: "Start tour" }));
    await user.click(screen.getByRole("button", { name: "Next" }));
    const step = within(screen.getByRole("dialog", { name: "Review workspace tour" }));
    expect(step.getByText(/Conversation/)).toBeInTheDocument();
    expect(step.getByText(/Threads/)).toBeInTheDocument();
    expect(step.queryByText(/Changes/)).toBeNull();
  });

  it("describes Changes once there are two Versions to compare", async () => {
    const user = userEvent.setup();
    openWorkspace({ versions: 2 });
    await user.click(screen.getByRole("button", { name: "Start tour" }));
    await user.click(screen.getByRole("button", { name: "Next" }));
    expect(within(screen.getByRole("dialog", { name: "Review workspace tour" })).getByText(/Changes/)).toBeInTheDocument();
  });

  it("finishes on the last step with Done, and closes", async () => {
    const user = userEvent.setup();
    openWorkspace();
    await user.click(screen.getByRole("button", { name: "Start tour" }));
    for (let i = 0; i < 2; i += 1) await user.click(screen.getByRole("button", { name: "Next" }));
    expect(progress()).toBe("Step 3 of 3");
    expect(screen.queryByRole("button", { name: "Next" })).toBeNull();
    await user.click(screen.getByRole("button", { name: "Done" }));
    expect(tourDialog()).toBeNull();
  });

  it("leaves out the paper's step when there is no paper", async () => {
    const user = userEvent.setup();
    openWorkspace({ reader: false });
    await user.click(screen.getByRole("button", { name: "Start tour" }));
    expect(progress()).toBe("Step 1 of 2");
    expect(stepTitle()).toBe("Review pane sections");
  });

  it("points a narrow workspace at the launcher, since the pane is closed", async () => {
    widthOf(700);
    const user = userEvent.setup();
    openWorkspace();
    await user.click(screen.getByRole("button", { name: "Take a tour" }));
    expect(progress()).toBe("Step 1 of 2");
    await user.click(screen.getByRole("button", { name: "Next" }));
    expect(stepTitle()).toBe("The review pane");
  });

  it("offers the tour on a narrow workspace too, where the pane is closed", async () => {
    widthOf(700);
    const user = userEvent.setup();
    openWorkspace();
    await user.click(screen.getByRole("button", { name: "Start tour" }));
    expect(progress()).toBe("Step 1 of 2");
  });

  it("starts the walk again when opening the pane changes which steps there are", async () => {
    widthOf(700);
    const user = userEvent.setup();
    openWorkspace();
    await user.click(screen.getByRole("button", { name: "Take a tour" }));
    await user.click(screen.getByRole("button", { name: "Next" }));
    expect(stepTitle()).toBe("The review pane");

    // The paper sits behind the open drawer, so its step goes.
    await user.click(screen.getByRole("button", { name: "Open review pane" }));
    expect(progress()).toBe("Step 1 of 2");
    expect(stepTitle()).toBe("Review pane sections");
  });

  it("ends on Your part, and has no step for a People & details column that is gone (IR-1094)", async () => {
    widthOf(1000);
    const user = userEvent.setup();
    openWorkspace();
    await user.click(screen.getByRole("button", { name: "Start tour" }));
    for (let i = 0; i < 2; i += 1) await user.click(screen.getByRole("button", { name: "Next" }));
    expect(stepTitle()).toBe("Your part");
  });

  it("mentions the columns button only where a tab may open on the right (IR-1094)", async () => {
    const user = userEvent.setup();
    for (const [width, offered] of [[1000, false], [1400, true]] as const) {
      widthOf(width);
      const { unmount } = openWorkspace();
      await user.click(screen.getByRole("button", { name: "Take a tour" }));
      await user.click(screen.getByRole("button", { name: "Next" }));
      const step = within(screen.getByRole("dialog", { name: "Review workspace tour" }));
      expect(step.getByText(/Details/)).toBeInTheDocument();
      expect(step.queryByText(/Columns button/) !== null).toBe(offered);
      unmount();
    }
  });
});

describe("leaving the tour (IR-997)", () => {
  it("skips at once, and puts focus back on Take a tour", async () => {
    const user = userEvent.setup();
    openWorkspace();
    await user.click(screen.getByRole("button", { name: "Start tour" }));
    await user.click(screen.getByRole("button", { name: "Next" }));
    await user.click(screen.getByRole("button", { name: "Skip tour" }));

    expect(tourDialog()).toBeNull();
    expect(screen.getByRole("button", { name: "Take a tour" })).toHaveFocus();
  });

  it("closes on Escape", async () => {
    const user = userEvent.setup();
    openWorkspace();
    await user.click(screen.getByRole("button", { name: "Start tour" }));
    await user.keyboard("{Escape}");
    expect(tourDialog()).toBeNull();
  });

  it("moves focus into the step on open, so Enter can go on", async () => {
    const user = userEvent.setup();
    openWorkspace();
    await user.click(screen.getByRole("button", { name: "Take a tour" }));
    expect(screen.getByRole("dialog", { name: "Review workspace tour" })).toContainElement(document.activeElement as HTMLElement);
  });

  it("leaves the reviewer on the tab they were reading", async () => {
    const user = userEvent.setup();
    openWorkspace();
    await user.click(screen.getByRole("tab", { name: /Threads/ }));
    await user.click(screen.getByRole("button", { name: "Take a tour" }));
    await user.click(screen.getByRole("button", { name: "Skip tour" }));

    expect(screen.getByRole("tab", { name: /Threads/ })).toHaveAttribute("aria-selected", "true");
    expect(api.reviewComments).toHaveBeenCalledTimes(1);
  });

  it("can be started again after it was skipped or completed", async () => {
    const user = userEvent.setup();
    openWorkspace();
    await user.click(screen.getByRole("button", { name: "Start tour" }));
    await user.click(screen.getByRole("button", { name: "Skip tour" }));
    await user.click(screen.getByRole("button", { name: "Take a tour" }));
    expect(progress()).toBe("Step 1 of 3");
  });

  it("has no blocking accessibility violations while open", async () => {
    const user = userEvent.setup();
    const { container } = openWorkspace();
    await user.click(screen.getByRole("button", { name: "Start tour" }));
    await expectNoBlockingA11yViolations(container);
  });
});
