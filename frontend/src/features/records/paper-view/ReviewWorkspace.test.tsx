/**
 * The author's Review tab gives the reader its action bar's height (IR-477;
 * spec Appendix K, amended).
 *
 * Below `reading-wide` the bar sticks over the bottom of the screen, and the
 * reader lands citations and counts find matches only above it. The bar
 * wraps to two rows on a phone, so its height is measured rather than
 * assumed. jsdom has no ResizeObserver and no layout: the one stubbed here
 * reports whatever border-box height the test gives it.
 */
import { afterEach, describe, expect, it, vi } from "vitest";

import { act, renderScreen, screen } from "@/test/render";
import type { Capability } from "@/features/records/capabilities";
import type { RecordDetail } from "@/types/records";

import { ReviewWorkspace } from "./ReviewWorkspace";

vi.mock("@/api/records", () => ({
  recordsApi: {
    tracker: vi.fn(() => new Promise(() => {})),
    documentRequestSlots: vi.fn(() => new Promise(() => {})),
  },
}));

const record = {
  id: 7,
  title: "Groundwater Recharge Mapping in Metro Cebu",
  can_request_document: ["ierc"],
  current_holders: [],
  versions: [],
} as unknown as RecordDetail;

afterEach(() => {
  vi.unstubAllGlobals();
});

/** A ResizeObserver whose targets are `height` tall, border box and all, until resized. */
function measureBarAs(height: number) {
  const observers = new Set<{ report: (next: number) => void }>();
  vi.stubGlobal(
    "ResizeObserver",
    class {
      private readonly targets = new Set<Element>();
      constructor(private readonly callback: ResizeObserverCallback) {
        observers.add(this);
      }
      report(next: number) {
        this.targets.forEach((target) =>
          this.callback(
            [{ target, borderBoxSize: [{ blockSize: next, inlineSize: 360 }] } as unknown as ResizeObserverEntry],
            this as unknown as ResizeObserver,
          ),
        );
      }
      observe(target: Element) {
        this.targets.add(target);
        this.report(height);
      }
      unobserve(target: Element) {
        this.targets.delete(target);
      }
      disconnect() {
        this.targets.clear();
      }
    },
  );
  return { resizeTo: (next: number) => observers.forEach((observer) => observer.report(next)) };
}

function openReviewTab(granted: Capability[], onBarInset: (px: number) => void) {
  return renderScreen(
    <ReviewWorkspace
      record={record}
      authorView
      can={new Set(granted)}
      reader={<div>The paper</div>}
      timelineVersion={0}
      onChanged={() => {}}
      onBarInset={onBarInset}
      documents={<p>Every document</p>}
      documentsOpen={false}
      onDocuments={() => {}}
    />,
  );
}

describe("the author's Review tab and the reader's bottom inset (IR-477)", () => {
  it("gives the reader the action bar's measured height", async () => {
    measureBarAs(112);
    const onBarInset = vi.fn();
    openReviewTab(["request_document"], onBarInset);

    expect(await screen.findByRole("toolbar", { name: "Review actions" })).toBeInTheDocument();
    expect(onBarInset).toHaveBeenLastCalledWith(112);
  });

  it("follows the bar as it wraps to another row or back", async () => {
    const bar = measureBarAs(60);
    const onBarInset = vi.fn();
    openReviewTab(["request_document"], onBarInset);
    await screen.findByRole("toolbar", { name: "Review actions" });
    expect(onBarInset).toHaveBeenLastCalledWith(60);

    act(() => bar.resizeTo(112));
    expect(onBarInset).toHaveBeenLastCalledWith(112);
  });

  it("gives nothing when there is no bar, because no review action is granted", () => {
    measureBarAs(112);
    const onBarInset = vi.fn();
    openReviewTab([], onBarInset);

    expect(screen.queryByRole("toolbar", { name: "Review actions" })).not.toBeInTheDocument();
    expect(onBarInset.mock.calls.every(([px]) => px === 0)).toBe(true);
  });

  it("takes the inset back when the Review tab closes", async () => {
    measureBarAs(112);
    const onBarInset = vi.fn();
    const { unmount } = openReviewTab(["request_document"], onBarInset);
    await screen.findByRole("toolbar", { name: "Review actions" });

    unmount();
    expect(onBarInset).toHaveBeenLastCalledWith(0);
  });
});
