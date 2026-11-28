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

import { ReviewWorkspaceLayout } from "./ReviewWorkspaceLayout";

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
    <ReviewWorkspaceLayout record={record(versions)} can={new Set(caps)} reader={reader ? <div>The paper</div> : null}
      timelineVersion={0} onChanged={() => {}} documents={null} />,
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

/** Every step's title, from the one shown to the last, leaving the tour on its last step. */
async function walk(user: ReturnType<typeof userEvent.setup>) {
  const titles = [stepTitle()];
  while (screen.queryByRole("button", { name: "Next" })) {
    await user.click(screen.getByRole("button", { name: "Next" }));
    titles.push(stepTitle());
  }
  return titles;
}

/** Shows the step titled `title`, by pressing Next. */
async function stepNamed(user: ReturnType<typeof userEvent.setup>, title: string) {
  while (stepTitle() !== title) await user.click(screen.getByRole("button", { name: "Next" }));
  return within(screen.getByRole("dialog", { name: "Review workspace tour" }));
}

const REVIEWER_WALK = [
  "The paper", "Where the review stands", "The pane's tabs",
  "Documents", "Conversation", "Threads", "Changes", "Details",
  "Your part", "How a review goes",
];

describe("walking through the tour (IR-997)", () => {
  it("shows one step at a time, with progress, Next and Previous", async () => {
    const user = userEvent.setup();
    openWorkspace();
    await user.click(screen.getByRole("button", { name: "Start tour" }));

    expect(progress()).toBe(`Step 1 of ${REVIEWER_WALK.length}`);
    expect(stepTitle()).toBe("The paper");
    expect(screen.getByRole("button", { name: "Previous" })).toBeDisabled();

    await user.click(screen.getByRole("button", { name: "Next" }));
    expect(progress()).toBe(`Step 2 of ${REVIEWER_WALK.length}`);
    expect(stepTitle()).toBe("Where the review stands");

    await user.click(screen.getByRole("button", { name: "Previous" }));
    expect(progress()).toBe(`Step 1 of ${REVIEWER_WALK.length}`);
  });

  it("gives every tab a step of its own, in the row's order (IR-1309)", async () => {
    const user = userEvent.setup();
    openWorkspace();
    await user.click(screen.getByRole("button", { name: "Start tour" }));
    expect(await walk(user)).toEqual(REVIEWER_WALK);
  });

  it("keeps a step for Changes on the first version too, since it is always a tab (IR-1139)", async () => {
    const user = userEvent.setup();
    openWorkspace({ versions: 1 });
    await user.click(screen.getByRole("button", { name: "Start tour" }));
    expect(await walk(user)).toContain("Changes");
  });

  it("finishes on the last step with Done, and closes", async () => {
    const user = userEvent.setup();
    openWorkspace();
    await user.click(screen.getByRole("button", { name: "Start tour" }));
    await walk(user);
    expect(progress()).toBe(`Step ${REVIEWER_WALK.length} of ${REVIEWER_WALK.length}`);
    expect(screen.queryByRole("button", { name: "Next" })).toBeNull();
    await user.click(screen.getByRole("button", { name: "Done" }));
    expect(tourDialog()).toBeNull();
  });

  it("leaves out the paper's step when there is no paper", async () => {
    const user = userEvent.setup();
    openWorkspace({ reader: false });
    await user.click(screen.getByRole("button", { name: "Start tour" }));
    expect(progress()).toBe(`Step 1 of ${REVIEWER_WALK.length - 1}`);
    expect(stepTitle()).toBe("Where the review stands");
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
    expect(progress()).toBe(`Step 1 of ${REVIEWER_WALK.length - 1}`);
    expect(stepTitle()).toBe("Where the review stands");
  });

  it("ends on Your part and how a review goes, with no People & details column step (IR-1094, IR-1309)", async () => {
    widthOf(1000);
    const user = userEvent.setup();
    openWorkspace();
    await user.click(screen.getByRole("button", { name: "Start tour" }));
    const titles = await walk(user);
    expect(titles.slice(-2)).toEqual(["Your part", "How a review goes"]);
    expect(titles).not.toContain("People & details");
    const step = within(screen.getByRole("dialog", { name: "Review workspace tour" }));
    expect(step.getByText("1. Claim or start it")).toBeInTheDocument();
    expect(step.getByText("3. Finish review")).toBeInTheDocument();
  });

  it("gives the columns button a step only where a tab may open on the right (IR-1094, IR-1309)", async () => {
    const user = userEvent.setup();
    for (const [width, offered] of [[1000, false], [1400, true]] as const) {
      widthOf(width);
      const { unmount } = openWorkspace();
      await user.click(screen.getByRole("button", { name: "Take a tour" }));
      expect((await walk(user)).includes("Two tabs side by side")).toBe(offered);
      unmount();
    }
  });

  it("describes a tab moved to the right column there, not in the row (IR-1309)", async () => {
    localStorage.setItem("iris-review-side-tab", "threads");
    widthOf(1400);
    const user = userEvent.setup();
    openWorkspace();
    await user.click(screen.getByRole("button", { name: "Take a tour" }));
    const titles = await walk(user);
    expect(titles).toContain("Threads, on the right");
    expect(titles).not.toContain("Threads");
  });
});

describe("what the steps explain (IR-1309)", () => {
  it("tells a reviewer who may start a thread how to comment on a passage", async () => {
    const user = userEvent.setup();
    openWorkspace({ caps: ["comment_review", "start_thread"] });
    await user.click(screen.getByRole("button", { name: "Start tour" }));
    const step = within(screen.getByRole("dialog", { name: "Review workspace tour" }));
    expect(step.getByText("Comment on a passage")).toBeInTheDocument();
    expect(step.getByText(/press C or the Comment button/)).toBeInTheDocument();
    expect(step.getByText("Pins")).toBeInTheDocument();
  });

  it("does not offer commenting on a passage to a reviewer who may not start a thread", async () => {
    const user = userEvent.setup();
    openWorkspace({ caps: ["comment_review"] });
    await user.click(screen.getByRole("button", { name: "Start tour" }));
    const step = within(screen.getByRole("dialog", { name: "Review workspace tour" }));
    expect(step.queryByText("Comment on a passage")).toBeNull();
    expect(step.getByText("Pins")).toBeInTheDocument();
  });

  it("explains drafts in Threads only while new threads can wait as drafts", async () => {
    const user = userEvent.setup();
    const cases: [Capability[], boolean][] = [
      [["comment_review", "start_thread"], false],
      [["comment_review", "start_thread", "finish_review"], true],
    ];
    for (const [caps, drafting] of cases) {
      const { unmount } = openWorkspace({ caps });
      await user.click(screen.getByRole("button", { name: "Take a tour" }));
      const step = await stepNamed(user, "Threads");
      expect(step.getByText("Start a thread")).toBeInTheDocument();
      expect(step.queryByText("Drafts") !== null).toBe(drafting);
      await user.click(screen.getByRole("button", { name: "Skip tour" }));
      unmount();
    }
  });

  it("explains the pane's header, with the resize edge only where it exists", async () => {
    const user = userEvent.setup();
    for (const [width, edge] of [[1000, true], [700, false]] as const) {
      widthOf(width);
      const { unmount } = openWorkspace();
      if (width === 700) await user.click(screen.getByRole("button", { name: "Open review pane" }));
      await user.click(screen.getByRole("button", { name: "Take a tour" }));
      const step = await stepNamed(user, "Where the review stands");
      expect(step.getByText("With …")).toBeInTheDocument();
      expect(step.queryByText("Pane width") !== null).toBe(edge);
      await user.click(screen.getByRole("button", { name: "Skip tour" }));
      unmount();
    }
  });

  it("no longer promises a fixed number of steps in the offer", () => {
    openWorkspace();
    expect(screen.getByRole("group", { name: "Guided tour" })).not.toHaveTextContent(/four-step/);
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
    expect(progress()).toBe(`Step 1 of ${REVIEWER_WALK.length}`);
  });

  it("has no blocking accessibility violations while open", async () => {
    const user = userEvent.setup();
    const { container } = openWorkspace();
    await user.click(screen.getByRole("button", { name: "Start tour" }));
    await expectNoBlockingA11yViolations(container);
  });
});
