import { useCallback, useEffect, useId, useState, type MouseEvent } from "react";
import { cn } from "@/lib/utils";
import { CONTROL_BASE, CONTROL_ON, CONTROL_OUTLINE } from "./controls";
import { RailHeading } from "./headings";
import { READING_HEADER_PX } from "./paneLayout";
import { focusFragmentTarget } from "./useFragmentFocus";

/**
 * "On this page" for a paper's Overview (IR-1000): a way to move between the
 * Abstract, AI Overview, Related works and Comments, and to see which of them
 * is being read.
 *
 * Two placements share one list. Wide, it sits at the top of the sticky Record
 * details column (`rail`), which is the side room the Overview already has;
 * narrow, or while Ask IRIS folds that column away, it is a row of chips above
 * the Abstract (`inline`) that wraps rather than scrolls sideways. The page
 * mounts both and CSS shows one, so each carries its own heading id.
 *
 * Links are real anchors, so they work from the keyboard and read as links.
 * They scroll to and focus the section through `focusFragmentTarget` and leave
 * the URL alone: the page keeps `?section=` and `?version=` there, and a
 * hash would hand the jump to `useFragmentFocus`, which is My Library's.
 */

export interface OverviewIndexItem {
  id: string;
  label: string;
}

/** The element ids the Overview's sections carry, which the index links to. */
export const OVERVIEW_TARGET = {
  abstract: "overview-abstract",
  ai: "overview-ai",
  related: "overview-related-works",
  comments: "overview-comments",
} as const;

/** Classes every target carries: below the sticky header once jumped to, and focusable without a ring. */
export const OVERVIEW_TARGET_CLASS = "scroll-mt-20 focus:outline-none";

/** The sections the index lists. Comments belong to published papers only. */
export function overviewIndexItems(published: boolean): OverviewIndexItem[] {
  return [
    { id: OVERVIEW_TARGET.abstract, label: "Abstract" },
    { id: OVERVIEW_TARGET.ai, label: "AI Overview" },
    { id: OVERVIEW_TARGET.related, label: "Related works" },
    ...(published ? [{ id: OVERVIEW_TARGET.comments, label: "Comments" }] : []),
  ];
}

/** A section is current once its top passes this line under the sticky header. */
const READ_LINE_PX = READING_HEADER_PX + 24;

/**
 * The section being read: the last one whose top is above the reading line, the
 * first before any is, and the last once the page is scrolled to its end (a
 * short last section never reaches the line). Without layout (jsdom, a hidden
 * pane) nothing can be measured, so it is the first.
 */
export function currentSection(ids: string[]): string | null {
  let current: string | null = null;
  let last: string | null = null;
  let measured = false;
  for (const id of ids) {
    const el = document.getElementById(id);
    if (!el) continue;
    const rect = el.getBoundingClientRect();
    if (rect.height > 0 || rect.top !== 0) measured = true;
    current ??= id;
    last = id;
    if (rect.top <= READ_LINE_PX) current = id;
  }
  if (!measured) return ids.find((id) => document.getElementById(id)) ?? null;
  const root = document.documentElement;
  if (window.scrollY > 0 && window.innerHeight + window.scrollY >= root.scrollHeight - 2) return last;
  return current;
}

/** Which of `ids` is current while `enabled`, and a way to say so at once after a jump. */
export function useCurrentSection(ids: string[], enabled: boolean): [string | null, (id: string) => void] {
  const key = ids.join("|");
  const [current, setCurrent] = useState<string | null>(null);

  useEffect(() => {
    if (!enabled) {
      setCurrent(null);
      return;
    }
    const list = key ? key.split("|") : [];
    let frame = 0;
    const update = () => {
      frame = 0;
      setCurrent(currentSection(list));
    };
    const schedule = () => {
      if (!frame) frame = window.requestAnimationFrame(update);
    };
    update();
    // Capture, so any scroll container the page sits in is heard, not only the window.
    document.addEventListener("scroll", schedule, { capture: true, passive: true });
    window.addEventListener("resize", schedule);
    // Sections load after the page does and move what is below them.
    const observer = new MutationObserver(schedule);
    observer.observe(document.body, { childList: true, subtree: true });
    return () => {
      if (frame) window.cancelAnimationFrame(frame);
      document.removeEventListener("scroll", schedule, { capture: true });
      window.removeEventListener("resize", schedule);
      observer.disconnect();
    };
  }, [key, enabled]);

  return [current, setCurrent];
}

interface OverviewIndexProps {
  items: OverviewIndexItem[];
  /** The id of the section being read, or null. */
  current: string | null;
  onJump: (id: string) => void;
  variant: "rail" | "inline";
  className?: string;
}

export function OverviewIndex({ items, current, onJump, variant, className }: OverviewIndexProps) {
  const headingId = useId();
  const jump = useCallback(
    (event: MouseEvent<HTMLAnchorElement>, id: string) => {
      // Plain clicks only: a modified click keeps the browser's own behaviour.
      if (event.defaultPrevented || event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) {
        return;
      }
      event.preventDefault();
      if (focusFragmentTarget(id)) onJump(id);
    },
    [onJump],
  );

  return (
    <nav aria-labelledby={headingId} className={cn(variant === "rail" ? "space-y-2" : "flex flex-wrap items-center gap-x-3 gap-y-2", className)}>
      <RailHeading id={headingId} className={variant === "inline" ? "shrink-0" : undefined}>
        On this page
      </RailHeading>
      <ul className={cn(variant === "rail" ? "space-y-0.5" : "flex flex-wrap gap-2")}>
        {items.map((item) => {
          const isCurrent = item.id === current;
          return (
            <li key={item.id} className="min-w-0">
              <a
                href={`#${item.id}`}
                aria-current={isCurrent ? "location" : undefined}
                onClick={(event) => jump(event, item.id)}
                className={cn(
                  CONTROL_BASE,
                  "focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand",
                  variant === "rail"
                    ? cn(
                        "w-full border-l-2 rounded-l-none px-3 hover:bg-stone-100",
                        isCurrent
                          ? "border-brand bg-brand-50 text-brand"
                          : "border-transparent text-stone-600 hover:text-stone-900",
                      )
                    : cn("px-3", isCurrent ? CONTROL_ON : CONTROL_OUTLINE),
                )}
              >
                {item.label}
              </a>
            </li>
          );
        })}
      </ul>
    </nav>
  );
}
