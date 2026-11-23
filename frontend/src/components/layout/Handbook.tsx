/**
 * A handbook page: a Contents rail beside one typeset column (Guidelines,
 * Setup and Workflow analytics). Guidelines and Setup are the same page in two
 * modes, read and edit, so RDCO edits exactly what everyone reads.
 *
 * The page is a container named `handbook`. From 52rem of its own width the
 * rail sits beside the column and stays in view while the column scrolls;
 * below that it is a wrapping row of links above the column. The container,
 * not the window, decides: the sidebar opening narrows the room as surely as a
 * smaller screen does.
 *
 * The caller owns the rail's semantics (a `nav` of links, or a `tablist`), so
 * this file only lays it out and draws its items.
 */
import { useEffect, useState, type ReactNode } from "react";

import { HERE } from "@/components/ui/highlightRoles";
import { COLOUR_TRANSITION, FOCUS_RING } from "@/components/ui/interaction";
import { cn } from "@/lib/utils";

export function Handbook({ rail, children }: { rail: ReactNode; children: ReactNode }) {
  return (
    <div className="[container-type:inline-size] [container-name:handbook]">
      <div className="grid gap-y-6 handbook-wide:grid-cols-[13rem_minmax(0,1fr)] handbook-wide:gap-x-12">
        <div className="handbook-wide:sticky handbook-wide:top-6 handbook-wide:self-start">{rail}</div>
        <div className="min-w-0">{children}</div>
      </div>
    </div>
  );
}

/** The rail's caption, e.g. "Record types". Plain words, sentence case. */
export function RailCaption({ id, children }: { id?: string; children: ReactNode }) {
  return (
    <p id={id} className="mb-2 hidden text-small font-medium text-stone-600 handbook-wide:block">
      {children}
    </p>
  );
}

/** The list a rail's items sit in: a wrapping row when narrow, a column beside the page. */
export const RAIL_LIST = "flex flex-wrap gap-2 handbook-wide:flex-col handbook-wide:gap-0.5";

/**
 * One rail item. Narrow, an outlined pill in the wrapping row; beside the page,
 * a full-width row. The item you are on takes the Here look (IR-1097): Desk
 * Stone fill and Ink text, never maroon.
 */
export function railItemClass(here: boolean): string {
  return cn(
    "block rounded-full px-3 py-1.5 text-small ring-1 ring-stone-300 touch:min-h-11 touch:py-2.5",
    "handbook-wide:rounded-control handbook-wide:py-2 handbook-wide:ring-0",
    here
      ? HERE
      : "font-medium text-stone-700 hover:bg-stone-100 hover:text-stone-900",
    COLOUR_TRANSITION,
    FOCUS_RING,
  );
}

/**
 * Which of the page's sections is being read: the last one whose top has
 * passed a line a quarter of the way down the window, else the first. Reads
 * nothing where the browser can't observe (tests, old browsers), and then the
 * first section stays marked.
 */
export function useSectionInView(ids: string[]): string | null {
  const [current, setCurrent] = useState<string | null>(ids[0] ?? null);
  const key = ids.join("|");

  useEffect(() => {
    setCurrent(ids[0] ?? null);
    if (typeof window === "undefined" || typeof IntersectionObserver === "undefined" || ids.length === 0) return;
    const pick = () => {
      const line = window.innerHeight * 0.25;
      let found = ids[0];
      for (const id of ids) {
        const el = document.getElementById(id);
        if (el && el.getBoundingClientRect().top <= line) found = id;
      }
      // At the very bottom the last section may never reach the line.
      if (window.innerHeight + window.scrollY >= document.documentElement.scrollHeight - 2) {
        found = ids[ids.length - 1];
      }
      setCurrent(found);
    };
    const observer = new IntersectionObserver(pick, { rootMargin: "0px 0px -60% 0px", threshold: [0, 1] });
    for (const id of ids) {
      const el = document.getElementById(id);
      if (el) observer.observe(el);
    }
    window.addEventListener("scroll", pick, { passive: true });
    pick();
    return () => {
      observer.disconnect();
      window.removeEventListener("scroll", pick);
    };
    // `key` stands for `ids`, whose identity changes every render.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key]);

  return current;
}
