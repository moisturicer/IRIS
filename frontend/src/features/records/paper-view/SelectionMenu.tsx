/**
 * What the reader offers for a selected passage (IR-583, IR-581, ADR-065).
 *
 * One menu for every action on a selection: *Save highlight* and *Ask about
 * selection*. An action is data the page hands the reader, so a later slice
 * adds its own entry to the list instead of building a second menu, and this
 * file never learns what an action does.
 *
 * It floats over the paper, so it is the one thing here that lifts: a white
 * pill with a soft shadow and a hairline, actions divided by a hairline, and a
 * short rise into place (none under reduced motion).
 */
import type { ReactNode } from "react";

import { FOCUS_RING } from "@/components/ui/interaction";
import { cn } from "@/lib/utils";

import { CONTROL_SIZE } from "./controls";
import type { Passage } from "./threads/passage";

export interface SelectionAction {
  id: string;
  /** The button's accessible name. */
  label: string;
  /** A Font Awesome class, e.g. `fa-highlighter`, or a drawn mark. */
  icon: string | ReactNode;
  /**
   * Runs on the passage, with the Manuscript revision the paper was opened at
   * (null where the server named none). The reader never decides what is done.
   */
  run: (passage: Passage, manuscriptRevision: string | null) => void;
}

/** Where the menu rests: just under the passage, kept inside the window. */
export interface MenuPosition {
  top: number;
  left: number;
}

const MENU_HEIGHT = 52;
const MENU_WIDTH = 340;
const GAP = 8;
const EDGE = 8;

/** The menu's corner for a passage whose last line ends at `rect`, clamped to the window. */
export function menuPosition(rect: { left: number; bottom: number }, viewport: { width: number; height: number }): MenuPosition {
  const top = Math.min(Math.max(EDGE, rect.bottom + GAP), Math.max(EDGE, viewport.height - MENU_HEIGHT - EDGE));
  const left = Math.min(Math.max(EDGE, rect.left), Math.max(EDGE, viewport.width - MENU_WIDTH - EDGE));
  return { top, left };
}

/** The reader's own highlight, as a swatch of the colour it is drawn in. */
export function HighlightSwatch({ className }: { className?: string }) {
  return <span aria-hidden className={cn("highlight-swatch inline-block size-3.5 shrink-0 rounded-full", className)} />;
}

export function SelectionMenu({ actions, position, onChoose }: {
  actions: SelectionAction[];
  position: MenuPosition | null;
  onChoose: (action: SelectionAction) => void;
}) {
  if (actions.length === 0) return null;
  return (
    <div
      role="group"
      aria-label="Selected text actions"
      className={cn(
        "selection-menu z-20 flex items-center gap-0.5 rounded-full bg-white p-1",
        // Beside the passage when it is placed; otherwise a plain row under the toolbar.
        position ? "fixed" : "sticky top-2 mx-auto w-fit",
      )}
      style={position ? { top: position.top, left: position.left } : undefined}
    >
      {actions.map((action, n) => (
        <span key={action.id} className="flex items-center gap-0.5">
          {n > 0 && <span aria-hidden className="mx-0.5 h-5 w-px bg-stone-200" />}
          <button
            type="button"
            // Pressing it must not drop the selection it acts on.
            onMouseDown={(e) => e.preventDefault()}
            onClick={() => onChoose(action)}
            className={cn(
              "inline-flex items-center gap-2 rounded-full px-3.5 text-small font-semibold text-stone-800",
              "transition-colors duration-150 hover:bg-stone-100 hover:text-stone-900 active:bg-stone-200",
              "motion-reduce:transition-none",
              CONTROL_SIZE, FOCUS_RING,
            )}
          >
            {typeof action.icon === "string"
              ? <i className={cn("fas text-small text-stone-500", action.icon)} aria-hidden />
              : action.icon}
            {action.label}
          </button>
        </span>
      ))}
    </div>
  );
}
