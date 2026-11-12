import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";

import { FOCUS_RING } from "@/components/ui/interaction";
import { useDialogFocus } from "@/hooks/useDialogFocus";
import { cn } from "@/lib/utils";

import type { TourStep } from "./tourSteps";

const MARGIN = 12;
const CARD_WIDTH = 320;
const BUTTON = "inline-flex items-center justify-center min-h-11 px-4 rounded-full text-small font-semibold " +
  "disabled:opacity-60 disabled:cursor-not-allowed";

interface Box { top: number; left: number; width: number; height: number }

/**
 * A target counts only while a reviewer could see it: in the page, and not
 * under an inert or hidden ancestor (the review pane is both while a narrow
 * window keeps it closed). Layout is not consulted, so the rule is the same
 * with or without it.
 */
function reachable(id: string): HTMLElement | null {
  const el = document.getElementById(id);
  return el && !el.closest('[inert],[aria-hidden="true"]') ? el : null;
}

/** Below the target if the card fits, else above, else docked to the screen's foot. */
function cardPosition(target: Box | null, card: { width: number; height: number }) {
  const vw = window.innerWidth;
  const vh = window.innerHeight;
  const width = Math.min(CARD_WIDTH, vw - MARGIN * 2);
  if (!target) return { top: Math.max(MARGIN, (vh - card.height) / 2), left: Math.max(MARGIN, (vw - width) / 2), width };
  const below = target.top + target.height + MARGIN;
  const above = target.top - MARGIN - card.height;
  const top = below + card.height <= vh - MARGIN ? below : above >= MARGIN ? above : vh - card.height - MARGIN;
  const left = Math.min(Math.max(target.left, MARGIN), Math.max(MARGIN, vw - width - MARGIN));
  return { top: Math.max(MARGIN, top), left, width };
}

export interface GuidedTourProps {
  steps: readonly TourStep[];
  /** Where focus goes back to on close. */
  opener: HTMLElement | null;
  onClose: () => void;
}

/**
 * A walk through the workspace, one highlighted area at a time (IR-997).
 *
 * Deliberately **not modal**: the highlight is drawn, never a layer that takes
 * clicks, so a target that cannot be found or a tour left open can never trap
 * the reviewer behind an overlay. The card is a dialog that takes focus on
 * open, keeps Tab inside, closes on Escape and hands focus back to its opener
 * (`useDialogFocus`). It reads and writes nothing about the review.
 *
 * A step whose target is not reachable is left out of the walk -- and of its
 * progress count -- each render, so a window resized or a pane opened mid-tour
 * drops or restores steps rather than pointing at nothing. With none left it
 * closes itself.
 */
export function GuidedTour({ steps, opener, onClose }: GuidedTourProps) {
  const panel = useRef<HTMLDivElement>(null);
  const primary = useRef<HTMLButtonElement>(null);
  const [index, setIndex] = useState(0);
  const [box, setBox] = useState<Box | null>(null);
  const [card, setCard] = useState({ width: CARD_WIDTH, height: 200 });
  // Read from the page on purpose: reachability is a fact about the DOM now.
  const usable = steps.filter((s) => reachable(s.target));
  const at = Math.min(index, usable.length - 1);
  const step = usable[at];
  const last = at === usable.length - 1;

  useDialogFocus(true, panel, onClose, opener);
  useEffect(() => {
    // The default would land on the first control, which is Skip tour.
    primary.current?.focus();
  }, []);
  useEffect(() => {
    // Previous disables itself on the first step and Next becomes Done on the
    // last: if the control that had focus went inert, keep focus in the card.
    if (!panel.current?.contains(document.activeElement)) primary.current?.focus();
  }, [at]);
  useEffect(() => {
    if (!step) onClose();
  }, [step, onClose]);

  const targetId = step?.target;
  useLayoutEffect(() => {
    const measure = () => {
      const el = targetId ? reachable(targetId) : null;
      if (el) {
        const r = el.getBoundingClientRect();
        setBox({ top: r.top, left: r.left, width: r.width, height: r.height });
      } else {
        setBox(null);
      }
      if (panel.current) setCard({ width: panel.current.offsetWidth, height: panel.current.offsetHeight });
    };
    const el = targetId ? reachable(targetId) : null;
    if (typeof el?.scrollIntoView === "function") el.scrollIntoView({ block: "nearest", inline: "nearest" });
    measure();
    window.addEventListener("resize", measure);
    window.addEventListener("scroll", measure, true);
    return () => {
      window.removeEventListener("resize", measure);
      window.removeEventListener("scroll", measure, true);
    };
  }, [targetId, step?.body]);

  if (!step) return null;
  const place = cardPosition(box, card);

  return createPortal(
    <>
      {box && (
        <div aria-hidden className="fixed z-[60] pointer-events-none rounded-lg ring-2 ring-brand"
          style={{ top: box.top - 4, left: box.left - 4, width: box.width + 8, height: box.height + 8,
            boxShadow: "0 0 0 9999px rgb(41 37 36 / .4)" }} />
      )}
      <div ref={panel} role="dialog" aria-label="Review workspace tour" tabIndex={-1}
        className="fixed z-[61] rounded-2xl bg-white ring-1 ring-stone-200 shadow-card-md p-4 text-stone-700"
        style={{ top: place.top, left: place.left, width: place.width }}>
        <div aria-live="polite">
          <p className="text-2xs font-semibold uppercase tracking-wider text-stone-600">Step {at + 1} of {usable.length}</p>
          <h2 className="font-display text-lg font-semibold text-stone-900 mt-1">{step.title}</h2>
          <p className="mt-1.5 text-small">{step.body}</p>
          {step.items && (
            <ul className="mt-2 space-y-1 text-small">
              {step.items.map((item) => (
                <li key={item.name}><strong className="font-semibold text-stone-900">{item.name}</strong>{" "}{item.text}</li>
              ))}
            </ul>
          )}
        </div>
        <div className="mt-3 flex flex-wrap items-center gap-2">
          <button type="button" onClick={onClose}
            className={cn(BUTTON, FOCUS_RING, "px-2 text-stone-700 hover:text-stone-900 underline underline-offset-2")}>
            Skip tour
          </button>
          <span className="flex-1" />
          <button type="button" disabled={at === 0} onClick={() => setIndex(at - 1)}
            className={cn(BUTTON, FOCUS_RING, "ring-1 ring-stone-300 text-stone-700 hover:bg-stone-100")}>
            Previous
          </button>
          <button ref={primary} type="button" onClick={() => (last ? onClose() : setIndex(at + 1))}
            className={cn(BUTTON, FOCUS_RING, "bg-brand text-white hover:bg-brand-light")}>
            {last ? "Done" : "Next"}
          </button>
        </div>
      </div>
    </>,
    document.body,
  );
}
