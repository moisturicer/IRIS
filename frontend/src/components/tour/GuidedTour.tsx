import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";

import { FOCUS_RING } from "@/components/ui/interaction";
import { PILL_PRIMARY, PILL_SECONDARY } from "@/components/ui/pillStyles";
import { useDialogFocus } from "@/hooks/useDialogFocus";
import { cn } from "@/lib/utils";

import { reachable } from "./reachable";
import type { TourStep } from "./types";

export type { TourStep } from "./types";

const MARGIN = 12;
// Wide enough for a step's list of controls (IR-1309); a long step scrolls inside the card.
const CARD_WIDTH = 360;

interface Box { top: number; left: number; width: number; height: number }


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
  /** The card's accessible name, such as "Review workspace tour". */
  label: string;
  /** Where focus goes back to on close. */
  opener: HTMLElement | null;
  onClose: () => void;
  /**
   * Called once, when the first step is drawn (IR-1342). A tour that closes
   * itself because no target was reachable never calls it, so a caller can
   * tell a tour that was shown from one that never was.
   */
  onShown?: () => void;
  /**
   * Where the tour is drawn. `document.body` by default. A tour over a modal
   * dialog is drawn inside the dialog's panel, so assistive technology that
   * honours `aria-modal` still reaches it (IR-1342, Publish).
   */
  container?: Element | null;
}

/**
 * A walk through a page, one highlighted area at a time (IR-997; shared by the
 * student tours since IR-1342).
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
export function GuidedTour({ steps, label, opener, onClose, onShown, container }: GuidedTourProps) {
  const panel = useRef<HTMLDivElement>(null);
  const primary = useRef<HTMLButtonElement>(null);
  // The step is remembered by id, not position: opening the pane or resizing
  // changes which steps are reachable, and a position would then skip or repeat one.
  const [cursor, setCursor] = useState<string | null>(null);
  const [box, setBox] = useState<Box | null>(null);
  const [card, setCard] = useState({ width: CARD_WIDTH, height: 200 });
  // Read from the page on purpose: reachability is a fact about the DOM now.
  const usable = steps.filter((s) => reachable(s.target));
  const found = usable.findIndex((s) => s.id === cursor);
  // A step that vanished (the launcher, once the pane is open) restarts the walk.
  const at = Math.max(found, 0);
  const goTo = (n: number) => setCursor(usable[n].id);
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
  const shownRef = useRef(false);
  const hasStep = Boolean(step);
  useEffect(() => {
    if (!hasStep || shownRef.current) return;
    shownRef.current = true;
    onShown?.();
  }, [hasStep, onShown]);

  const targetId = step?.target;
  useLayoutEffect(() => {
    const find = () => (targetId ? reachable(targetId) : null);
    const measure = () => {
      const el = find();
      if (el) {
        const r = el.getBoundingClientRect();
        setBox({ top: r.top, left: r.left, width: r.width, height: r.height });
      } else {
        setBox(null);
      }
      if (panel.current) setCard({ width: panel.current.offsetWidth, height: panel.current.offsetHeight });
    };
    const el = find();
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
        // The maroon edge is an outline, not a ring: Tailwind draws a ring with
        // box-shadow, which the overlay's own box-shadow below replaced (IR-1344).
        <div aria-hidden className="fixed z-[60] pointer-events-none rounded-spotlight outline outline-2 outline-brand"
          style={{ top: box.top - 4, left: box.left - 4, width: box.width + 8, height: box.height + 8,
            boxShadow: "0 0 0 9999px rgb(41 37 36 / .4)" }} />
      )}
      <div ref={panel} role="dialog" aria-label={label} tabIndex={-1}
        className="fixed z-[61] rounded-card bg-white ring-1 ring-stone-200 shadow-card-md p-4 text-stone-700"
        style={{ top: place.top, left: place.left, width: place.width, maxHeight: `calc(100vh - ${MARGIN * 2}px)`, overflowY: "auto" }}>
        <div aria-live="polite">
          <p className="text-2xs font-semibold text-stone-600">Step {at + 1} of {usable.length}</p>
          <h2 className="font-display text-lg font-semibold text-stone-900 mt-1">{step.title}</h2>
          <p className="mt-1.5 text-small">{step.body}</p>
          {step.items && (
            <ul className="mt-2 space-y-1.5 text-small">
              {step.items.map((item) => (
                <li key={item.name}><strong className="font-semibold text-stone-900">{item.name}</strong>{" "}{item.text}</li>
              ))}
            </ul>
          )}
        </div>
        <div className="mt-3 flex flex-wrap items-center gap-2">
          <button type="button" onClick={onClose}
            className={cn("inline-flex items-center min-h-11 px-2 rounded-full text-sm font-semibold text-stone-700 hover:text-stone-900 underline underline-offset-2", FOCUS_RING)}>
            Skip tour
          </button>
          <span className="flex-1" />
          <button type="button" disabled={at === 0} onClick={() => goTo(at - 1)}
            className={cn(PILL_SECONDARY, FOCUS_RING)}>
            Previous
          </button>
          <button ref={primary} type="button" onClick={() => (last ? onClose() : goTo(at + 1))}
            className={cn(PILL_PRIMARY, FOCUS_RING)}>
            {last ? "Done" : "Next"}
          </button>
        </div>
      </div>
    </>,
    container ?? document.body,
  );
}
