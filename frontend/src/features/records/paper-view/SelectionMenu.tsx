/**
 * What the reader offers for a selected passage (IR-583, ADR-065).
 *
 * One menu for every action on a selection: *Save highlight* now, and *Ask
 * about selection* when IR-581 lands. An action is data the page hands the
 * reader, so a later slice adds its own entry to the list instead of building a
 * second menu, and this file never learns what an action does.
 */
import { cn } from "@/lib/utils";

import { CONTROL_BASE, CONTROL_OUTLINE } from "./controls";
import type { Passage } from "./threads/passage";

export interface SelectionAction {
  id: string;
  /** The button's accessible name. */
  label: string;
  /** A Font Awesome class, e.g. `fa-highlighter`. */
  icon: string;
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

const MENU_HEIGHT = 56;
const MENU_WIDTH = 220;
const GAP = 6;
const EDGE = 8;

/** The menu's corner for a passage whose last line ends at `rect`, clamped to the window. */
export function menuPosition(rect: { left: number; bottom: number }, viewport: { width: number; height: number }): MenuPosition {
  const top = Math.min(Math.max(EDGE, rect.bottom + GAP), Math.max(EDGE, viewport.height - MENU_HEIGHT - EDGE));
  const left = Math.min(Math.max(EDGE, rect.left), Math.max(EDGE, viewport.width - MENU_WIDTH - EDGE));
  return { top, left };
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
        "z-20 flex flex-wrap gap-1 rounded-xl border border-stone-300 bg-white p-1 shadow-card",
        // Beside the passage when it is placed; otherwise a plain row under the toolbar.
        position ? "fixed" : "sticky top-2 mx-auto w-fit",
      )}
      style={position ? { top: position.top, left: position.left } : undefined}
    >
      {actions.map((action) => (
        <button
          key={action.id}
          type="button"
          // Pressing it must not drop the selection it acts on.
          onMouseDown={(e) => e.preventDefault()}
          onClick={() => onChoose(action)}
          className={cn("px-3", CONTROL_BASE, CONTROL_OUTLINE)}
        >
          <i className={cn("fas", action.icon)} aria-hidden />
          {action.label}
        </button>
      ))}
    </div>
  );
}
