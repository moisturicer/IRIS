// The measurements behind the viewport matrix (IR-910) and the journeys' 360px
// reflow check (a11y.reflow360). One definition of "this page scrolls sideways"
// and "this control can be reached", so the two cannot drift apart.
import type { Locator, Page } from "@playwright/test";

/**
 * The widths the matrix runs at: the WCAG 1.4.10 reflow width, a tablet, the
 * standard laptop and the widest the design targets (IR-897). Heights are
 * ordinary device heights; nothing here depends on them.
 */
export const VIEWPORTS = [
  { name: "360", width: 360, height: 740 },
  { name: "768", width: 768, height: 1024 },
  { name: "1280", width: 1280, height: 800 },
  { name: "1745", width: 1745, height: 1000 },
] as const;

export interface OverflowReport {
  /** Pixels the page is wider than the window. 0 means it does not scroll sideways. */
  overflow: number;
  /** The outermost elements that stick out, widest first. A diagnosis; the verdict is `overflow`. */
  culprits: string[];
}

/** WCAG 1.4.10: does the page as a whole scroll sideways? Scroll containers inside it do not count. */
export async function measureOverflow(page: Page): Promise<OverflowReport> {
  return page.evaluate(() => {
    const width = document.documentElement.clientWidth;
    const overflow = document.documentElement.scrollWidth - width;
    const describe = (el: Element) => {
      const id = el.id ? `#${el.id}` : "";
      const cls = typeof el.className === "string" && el.className.trim()
        ? "." + el.className.trim().split(/\s+/).slice(0, 4).join(".") : "";
      return `${el.tagName.toLowerCase()}${id}${cls}`;
    };
    // An element only counts when its parent does not also stick out: the
    // outermost one is the thing to fix, its children merely follow it.
    // An element inside a box that clips sideways is not what widens the page,
    // however far right it sits -- with one catch: an absolutely positioned
    // element is clipped only by a box that is, or contains, its containing
    // block. A scroll container that is not itself positioned lets its
    // `position: absolute` children (an `sr-only` span) escape and widen the page.
    const clipped = (el: Element) => {
      let block: Element | null = null;
      if (getComputedStyle(el).position === "absolute") {
        block = el.parentElement;
        while (block && block !== document.body && getComputedStyle(block).position === "static") block = block.parentElement;
      }
      for (let p = el.parentElement; p && p !== document.body; p = p.parentElement) {
        if (getComputedStyle(p).overflowX === "visible") continue;
        if (!block || block === document.body || p.contains(block)) return true;
      }
      return false;
    };
    const culprits = overflow > 0
      ? Array.from(document.body.querySelectorAll("*"))
        .map((el) => ({ el, right: el.getBoundingClientRect().right }))
        .filter(({ el, right }) => right > width + 1 && !clipped(el) && (el.parentElement?.getBoundingClientRect().right ?? 0) <= width + 1)
        .sort((a, b) => b.right - a.right)
        .slice(0, 3)
        .map(({ el, right }) => `${describe(el)} (right edge ${Math.round(right)}px)`)
      : [];
    return { overflow, culprits };
  });
}

export interface Reachability {
  reachable: boolean;
  /** Why not, in a sentence a reviewer can act on. Empty when reachable. */
  reason: string;
}

/**
 * Can a person get to this control? It has to exist, sit inside the window
 * sideways once scrolled to (a page cannot be scrolled sideways, so a control
 * past the edge is gone), and be the thing under its own centre point -- not
 * hidden behind a sticky header, a drawer or a scrim.
 */
export async function checkReachable(target: Locator): Promise<Reachability> {
  const first = target.first();
  if ((await target.count()) === 0) return { reachable: false, reason: "not found on the screen" };
  await first.scrollIntoViewIfNeeded();
  if (!(await first.isVisible())) return { reachable: false, reason: "found but not visible" };
  return first.evaluate((el) => {
    // scrollIntoView will have dragged a sideways-overflowing page along with
    // it; undo that, because the standard is that nobody should have to.
    window.scrollTo(0, window.scrollY);
    const box = el.getBoundingClientRect();
    const width = document.documentElement.clientWidth;
    if (box.width === 0 || box.height === 0) return { reachable: false, reason: "has no size" };
    if (box.left < -1 || box.right > width + 1) {
      return { reachable: false, reason: `sticks out sideways (${Math.round(box.left)}px to ${Math.round(box.right)}px of ${width}px)` };
    }
    const x = box.left + box.width / 2;
    const y = Math.min(Math.max(box.top + box.height / 2, 0), window.innerHeight - 1);
    const top = document.elementFromPoint(x, y);
    if (!top || !(el === top || el.contains(top))) {
      const named = top ? `${top.tagName.toLowerCase()}${top.id ? `#${top.id}` : ""}` : "nothing";
      return { reachable: false, reason: `covered by ${named} at its centre` };
    }
    return { reachable: true, reason: "" };
  });
}

export interface TableReport {
  /** `fits`: no wider than its container. `scrolls`: wider, and its container scrolls sideways. `clipped`: wider and cut off. */
  behaviour: "fits" | "scrolls" | "clipped";
  tableWidth: number;
  containerWidth: number;
}

/** What a data table does when the window is narrower than it is. */
export async function describeTable(table: Locator): Promise<TableReport> {
  return table.first().evaluate((el) => {
    const tableWidth = Math.round(el.getBoundingClientRect().width);
    let container: HTMLElement | null = el.parentElement;
    while (container && container !== document.body) {
      const overflowX = getComputedStyle(container).overflowX;
      if (overflowX !== "visible") break;
      container = container.parentElement;
    }
    const box = container ?? document.body;
    const containerWidth = Math.round(box.clientWidth);
    const overflowX = getComputedStyle(box).overflowX;
    const scrollable = overflowX === "auto" || overflowX === "scroll";
    const behaviour = tableWidth <= containerWidth + 1 ? "fits" : scrollable ? "scrolls" : "clipped";
    return { behaviour, tableWidth, containerWidth } as TableReport;
  });
}
