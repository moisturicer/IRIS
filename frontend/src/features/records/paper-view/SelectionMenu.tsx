/**
 * What the reader offers for a selected passage (IR-583, IR-581, ADR-065 §8).
 *
 * One small composer under the passage, in Ask IRIS's own look: a line to
 * type in, a switch between what the passage is for (Ask IRIS, Highlight) and
 * one round Send. Each mode is an action the page hands the reader, so a later
 * slice adds its own entry instead of building a second menu, and this file
 * never learns what an action does.
 *
 * It floats over the paper, so it is the one thing here that lifts: a white
 * card with a soft shadow and a hairline, rising into place (none under
 * reduced motion). Enter sends; Escape closes it and drops the selection.
 */
import { useEffect, useId, useRef, useState, type ReactNode, type Ref } from "react";

import { FOCUS_RING } from "@/components/ui/interaction";
import { cn } from "@/lib/utils";

import { CONTROL_SIZE, CONTROL_SQUARE } from "./controls";
import type { Passage } from "./threads/passage";

export interface SelectionAction {
  id: string;
  /** Send's accessible name in this mode, e.g. "Save highlight". */
  label: string;
  /** The switch's name for this mode, e.g. "Highlight"; `label` where absent. */
  short?: string;
  /** What the line says before anything is typed. */
  placeholder?: string;
  /** A Font Awesome class, e.g. `fa-highlighter`, or a drawn mark. */
  icon: string | ReactNode;
  /** Send's Font Awesome class in this mode; an arrow where absent. */
  sendIcon?: string;
  /**
   * Runs on the passage, with the Manuscript revision the paper was opened at
   * (null where the server named none) and what the reader typed, trimmed
   * (empty when nothing). The reader never decides what is done.
   */
  run: (passage: Passage, manuscriptRevision: string | null, text: string) => void;
}

/** Where the composer rests: just under the passage, kept inside the window. */
export interface MenuPosition {
  top: number;
  left: number;
}

const MENU_HEIGHT = 112;
const MENU_WIDTH = 384;
const GAP = 10;
const EDGE = 8;

/** The composer's corner for a passage whose last line ends at `rect`, clamped to the window. */
export function menuPosition(rect: { left: number; bottom: number }, viewport: { width: number; height: number }): MenuPosition {
  const top = Math.min(Math.max(EDGE, rect.bottom + GAP), Math.max(EDGE, viewport.height - MENU_HEIGHT - EDGE));
  const left = Math.min(Math.max(EDGE, rect.left), Math.max(EDGE, viewport.width - MENU_WIDTH - EDGE));
  return { top, left };
}

/** The reader's own highlight, as a swatch of the colour it is drawn in. */
export function HighlightSwatch({ className }: { className?: string }) {
  return <span aria-hidden className={cn("highlight-swatch inline-block size-3.5 shrink-0 rounded-full", className)} />;
}

const glyph = (icon: SelectionAction["icon"], className?: string) =>
  typeof icon === "string" ? <i className={cn("fas", icon, className)} aria-hidden /> : icon;

export function SelectionMenu({ actions, position, onChoose, onDismiss, onPress, menuRef }: {
  actions: SelectionAction[];
  position: MenuPosition | null;
  onChoose: (action: SelectionAction, text: string) => void;
  /** Escape: close it and let the passage go. */
  onDismiss?: () => void;
  /** A press inside it, before focus or the selection moves: the passage must stay. */
  onPress?: () => void;
  /** The composer itself, so the reader can tell focus inside it from a click on the paper. */
  menuRef?: Ref<HTMLDivElement>;
}) {
  const [modeId, setModeId] = useState(actions[0]?.id);
  const [text, setText] = useState("");
  const fieldId = useId();
  const field = useRef<HTMLInputElement>(null);
  const mode = actions.find((a) => a.id === modeId) ?? actions[0];
  // A fresh selection starts on the first mode with nothing typed.
  useEffect(() => { if (!actions.some((a) => a.id === modeId)) setModeId(actions[0]?.id); }, [actions, modeId]);
  if (!mode) return null;

  const send = () => onChoose(mode, text.trim());

  return (
    <div
      ref={menuRef}
      role="group"
      aria-label="Selected text actions"
      onKeyDown={(e) => { if (e.key === "Escape") { e.stopPropagation(); onDismiss?.(); } }}
      onPointerDownCapture={onPress}
      className={cn(
        "selection-menu z-[35] w-[min(24rem,calc(100vw-1rem))] rounded-card bg-white p-2",
        // Beside the passage when it is placed; otherwise under the toolbar.
        position ? "fixed" : "sticky top-2 mx-auto",
      )}
      style={position ? { top: position.top, left: position.left } : undefined}
    >
      <form onSubmit={(e) => { e.preventDefault(); send(); }}>
        <label htmlFor={fieldId} className="sr-only">{mode.placeholder ?? mode.label}</label>
        <input
          ref={field}
          id={fieldId}
          value={text}
          onChange={(e) => setText(e.target.value)}
          placeholder={mode.placeholder ?? mode.label}
          maxLength={4000}
          autoComplete="off"
          className="block w-full bg-transparent px-2.5 pb-2 pt-1.5 text-body text-stone-900 outline-none placeholder:text-stone-600"
        />
        <div className="flex items-center gap-2">
          {actions.length > 1 && (
            <div role="radiogroup" aria-label="What to do with the passage"
              className="inline-flex items-center rounded-full bg-stone-200/80 p-0.5 [box-shadow:inset_0_1px_2px_rgb(41_37_36/0.16)]">
              {actions.map((action) => {
                const on = action.id === mode.id;
                return (
                  <button
                    key={action.id}
                    type="button"
                    role="radio"
                    aria-checked={on}
                    // Choosing a mode must not drop the selection it acts on.
                    onMouseDown={(e) => e.preventDefault()}
                    onClick={() => { setModeId(action.id); field.current?.focus(); }}
                    className={cn(
                      "inline-flex items-center gap-1.5 rounded-full px-3 text-small font-semibold", CONTROL_SIZE,
                      "transition-colors duration-200 motion-reduce:transition-none",
                      on ? "bg-brand text-white shadow-sm" : "text-stone-600 hover:text-brand",
                      FOCUS_RING,
                    )}
                  >
                    {glyph(action.icon, on ? "text-white" : "text-stone-500")}
                    {action.short ?? action.label}
                  </button>
                );
              })}
            </div>
          )}
          <span className="flex-1" />
          <button
            type="submit"
            aria-label={mode.label}
            title={mode.label}
            onMouseDown={(e) => e.preventDefault()}
            className={cn(
              "grid shrink-0 place-items-center rounded-full bg-brand text-white", CONTROL_SQUARE,
              "transition-[background-color,transform] duration-150 hover:bg-brand-light active:scale-95 active:bg-brand-press",
              "motion-reduce:transition-none motion-reduce:active:scale-100",
              FOCUS_RING,
            )}
          >
            <i aria-hidden className={cn("fas text-small", mode.sendIcon ?? "fa-arrow-up")} />
          </button>
        </div>
      </form>
    </div>
  );
}
