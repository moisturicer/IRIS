/**
 * "On this page" for the paper Overview (IR-1000).
 *
 * jsdom has no layout, so which section is current while scrolling is driven
 * here by stubbed rectangles; where the index sits at each width is CSS and is
 * held by the page's own test file as class assertions, and by a browser.
 */
import { afterEach, describe, expect, it, vi } from "vitest";

import { expectNoBlockingA11yViolations } from "@/test/axe";
import { act, renderScreen, screen, userEvent, within } from "@/test/render";

import {
  OVERVIEW_TARGET,
  OverviewIndex,
  currentSection,
  overviewIndexItems,
  useCurrentSection,
} from "./OverviewIndex";

/** Give each section a measured top, as a scrolled page would. */
function layOut(tops: Record<string, number>) {
  for (const id of Object.keys(tops)) {
    const el = document.getElementById(id)!;
    vi.spyOn(el, "getBoundingClientRect").mockReturnValue({
      top: tops[id], height: 300, bottom: tops[id] + 300, left: 0, right: 600, width: 600, x: 0, y: tops[id],
      toJSON: () => ({}),
    });
  }
}

function Page({ published = true }: { published?: boolean }) {
  const items = overviewIndexItems(published);
  const [current, setCurrent] = useCurrentSection(items.map((i) => i.id), true);
  return (
    <>
      <OverviewIndex variant="inline" items={items} current={current} onJump={setCurrent} />
      {items.map((item) => (
        <section key={item.id} id={item.id} tabIndex={-1}>
          <h2>{item.label} body</h2>
        </section>
      ))}
    </>
  );
}

afterEach(() => {
  vi.restoreAllMocks();
});

describe("which sections the index lists", () => {
  it("is Abstract, AI Overview, Related works and Comments on a published paper", () => {
    expect(overviewIndexItems(true).map((i) => i.label)).toEqual([
      "Abstract",
      "AI Overview",
      "Related works",
      "Comments",
    ]);
  });

  it("leaves Comments out where the page has none, rather than linking to nothing", () => {
    expect(overviewIndexItems(false).map((i) => i.label)).toEqual(["Abstract", "AI Overview", "Related works"]);
  });
});

describe("the index", () => {
  it("is one named navigation landmark of links, each to its section", () => {
    renderScreen(<Page />);
    const nav = screen.getByRole("navigation", { name: "On this page" });
    const links = within(nav).getAllByRole("link");
    expect(links.map((l) => l.textContent)).toEqual(["Abstract", "AI Overview", "Related works", "Comments"]);
    expect(links.map((l) => l.getAttribute("href"))).toEqual(
      Object.values(OVERVIEW_TARGET).map((id) => `#${id}`),
    );
  });

  it("marks the first section current before anything can be measured", () => {
    renderScreen(<Page />);
    expect(screen.getByRole("link", { name: "Abstract" })).toHaveAttribute("aria-current", "location");
    expect(screen.getByRole("link", { name: "Comments" })).not.toHaveAttribute("aria-current");
  });

  it("takes keyboard focus in reading order and shows where it is", async () => {
    renderScreen(<Page />);
    await userEvent.tab();
    expect(screen.getByRole("link", { name: "Abstract" })).toHaveFocus();
    await userEvent.tab();
    const link = screen.getByRole("link", { name: "AI Overview" });
    expect(link).toHaveFocus();
    // A visible focus indicator is part of every link, not only on hover.
    expect(link.className).toContain("focus-visible:outline-2");
  });

  it("moves to the section on Enter, focuses it and marks it current, leaving the address alone", async () => {
    const scrollIntoView = vi.fn();
    window.HTMLElement.prototype.scrollIntoView = scrollIntoView;
    renderScreen(<Page />, { route: "/records/7?section=overview" });
    const before = window.location.href;

    await userEvent.tab();
    await userEvent.tab();
    await userEvent.keyboard("{Enter}");

    expect(document.getElementById(OVERVIEW_TARGET.ai)).toHaveFocus();
    expect(scrollIntoView).toHaveBeenCalledWith({ block: "start" });
    expect(screen.getByRole("link", { name: "AI Overview" })).toHaveAttribute("aria-current", "location");
    expect(screen.getByRole("link", { name: "Abstract" })).not.toHaveAttribute("aria-current");
    expect(window.location.href).toBe(before);
  });

  it("leaves a modified click to the browser", async () => {
    renderScreen(<Page />);
    const link = screen.getByRole("link", { name: "Related works" });
    const click = new MouseEvent("click", { bubbles: true, cancelable: true, ctrlKey: true });
    link.dispatchEvent(click);
    expect(click.defaultPrevented).toBe(false);
    expect(document.getElementById(OVERVIEW_TARGET.related)).not.toHaveFocus();
  });

  it("has no serious or critical accessibility violations, in either placement", async () => {
    const items = overviewIndexItems(true);
    const { container } = renderScreen(
      <>
        <OverviewIndex variant="inline" items={items} current={items[1].id} onJump={() => {}} />
        <OverviewIndex variant="rail" items={items} current={items[2].id} onJump={() => {}} />
      </>,
    );
    await expectNoBlockingA11yViolations(container);
  });
});

describe("which section is current", () => {
  it("is the last one whose top has passed the reading line", () => {
    renderScreen(<Page />);
    layOut({
      [OVERVIEW_TARGET.abstract]: -400,
      [OVERVIEW_TARGET.ai]: 40,
      [OVERVIEW_TARGET.related]: 700,
      [OVERVIEW_TARGET.comments]: 1200,
    });
    expect(currentSection(overviewIndexItems(true).map((i) => i.id))).toBe(OVERVIEW_TARGET.ai);
  });

  it("is the first while every section is still below the line", () => {
    renderScreen(<Page />);
    layOut({
      [OVERVIEW_TARGET.abstract]: 300,
      [OVERVIEW_TARGET.ai]: 700,
      [OVERVIEW_TARGET.related]: 1100,
      [OVERVIEW_TARGET.comments]: 1500,
    });
    expect(currentSection(overviewIndexItems(true).map((i) => i.id))).toBe(OVERVIEW_TARGET.abstract);
  });

  it("is the last one at the end of the page, though its top never reaches the line", () => {
    renderScreen(<Page />);
    layOut({
      [OVERVIEW_TARGET.abstract]: -1500,
      [OVERVIEW_TARGET.ai]: -1000,
      [OVERVIEW_TARGET.related]: -300,
      [OVERVIEW_TARGET.comments]: 400,
    });
    vi.spyOn(window, "scrollY", "get").mockReturnValue(900);
    vi.spyOn(window, "innerHeight", "get").mockReturnValue(700);
    vi.spyOn(document.documentElement, "scrollHeight", "get").mockReturnValue(1600);
    expect(currentSection(overviewIndexItems(true).map((i) => i.id))).toBe(OVERVIEW_TARGET.comments);
  });

  it("follows the page as it scrolls", async () => {
    vi.spyOn(window, "requestAnimationFrame").mockImplementation((cb) => {
      cb(0);
      return 1;
    });
    renderScreen(<Page />);
    layOut({
      [OVERVIEW_TARGET.abstract]: -500,
      [OVERVIEW_TARGET.ai]: -100,
      [OVERVIEW_TARGET.related]: 500,
      [OVERVIEW_TARGET.comments]: 1000,
    });
    await act(async () => {
      document.dispatchEvent(new Event("scroll"));
    });
    expect(screen.getByRole("link", { name: "AI Overview" })).toHaveAttribute("aria-current", "location");
  });

  it("skips a section the page does not have", () => {
    renderScreen(<Page published={false} />);
    layOut({
      [OVERVIEW_TARGET.abstract]: -900,
      [OVERVIEW_TARGET.ai]: -500,
      [OVERVIEW_TARGET.related]: -100,
    });
    expect(currentSection(overviewIndexItems(true).map((i) => i.id))).toBe(OVERVIEW_TARGET.related);
  });
});
