import { useId, type CSSProperties, type Ref } from "react";

import { Button } from "@/components/ui";
import { AskIrisMark } from "@/features/ai/components/AskIrisIcons";
import { cn } from "@/lib/utils";
import type { RecordDetail } from "@/types/records";

import { CONTROL_BASE, CONTROL_FILLED, CONTROL_OUTLINE } from "./controls";
import { ICON_BUTTON, ResizeEdge } from "./PaperChatDock";
import { MAX_NOTE_LENGTH, type ReadingNoteState } from "./useReadingNote";

interface NotesPanelProps {
  /** The record the page is showing. */
  record: RecordDetail;
  /** The note, held by the page so closing the panel keeps the draft. */
  note: ReadingNoteState;
  onClose: () => void;
  /** One view at a time (IR-569): the way back to the paper. */
  onBackToPaper?: () => void;
  /** Swap this panel's place for Ask IRIS. Absent where it is not offered. */
  onOpenAsk?: () => void;
  /** The panel itself, for the page to move focus into. */
  panelRef?: Ref<HTMLElement>;
  /** Over or instead of the paper (IR-569): a modal dialog, not a side panel. */
  modal?: boolean;
  style?: CSSProperties;
  /** Where the reader drags the panel's edge; absent where it is not a column. */
  resize?: { width: number; max: number; onChange: (width: number) => void };
  /** Positioning is the caller's job: the panel only styles its own interior. */
  className?: string;
}

/**
 * The reader's private note on this paper (IR-580, ADR-064): one focused
 * editor in the place Ask IRIS has, never a grid of cards. Autosave says
 * Saving, Saved or Could not save, and a note changed on another device shows
 * both texts and waits for the reader to choose.
 */
export function NotesPanel({ record, note, onClose, onBackToPaper, onOpenAsk, panelRef, modal, style, resize, className }: NotesPanelProps) {
  const headingId = useId();
  const editorId = useId();
  const hintId = useId();

  return (
    <aside ref={panelRef} style={style} tabIndex={-1} aria-labelledby={headingId}
      role={modal ? "dialog" : undefined} aria-modal={modal || undefined}
      className={cn("bg-canvas flex flex-col overflow-hidden focus:outline-none motion-safe:animate-panel-in", className)}>
      {resize && <ResizeEdge {...resize} label="Resize Notes" />}

      <div className="shrink-0 border-b border-stone-200 bg-stone-100 px-4 pb-3 pt-3">
        {onBackToPaper && <button type="button" onClick={onBackToPaper}
          className={cn("reading-split:hidden -ml-2 mb-1 px-2 text-brand", CONTROL_BASE)}>
          <i className="fas fa-arrow-left text-2xs" aria-hidden />Back to paper
        </button>}
        <div className="flex items-center gap-2">
          <i className="fas fa-note-sticky shrink-0 text-brand" aria-hidden />
          <h2 id={headingId} className="font-display text-xl font-semibold leading-none text-stone-900">Notes</h2>
          <span className="flex-1" />
          {onOpenAsk && <button type="button" onClick={onOpenAsk} aria-label="Ask IRIS" title="Ask IRIS about this paper"
            className={ICON_BUTTON}>
            <AskIrisMark className="h-4 w-4" />
          </button>}
          <Button variant="ghost" size="icon" onClick={onClose} aria-label="Close Notes" className="-mr-2">
            <i className="fas fa-xmark" aria-hidden />
          </Button>
        </div>
        <p className="mt-2 truncate text-2xs text-stone-600">{record.title}</p>
        <p id={hintId} className="mt-1 text-2xs text-stone-600">
          <i className="fas fa-lock mr-1" aria-hidden />
          Private: only you can read your notes. Not staff, the paper’s authors or Ask IRIS.
        </p>
      </div>

      <div className="flex min-h-0 flex-1 flex-col">
        {(note.phase === "idle" || note.phase === "loading") && (
          <p className="px-4 py-6 text-small text-stone-600">Opening your note…</p>
        )}

        {note.phase === "load_failed" && (
          <div className="px-4 py-6">
            <p className="text-small text-stone-900">Could not load your note.</p>
            <p className="mt-1 text-2xs text-stone-600">Nothing was changed. Notes stay closed until it loads, so nothing can overwrite it.</p>
            <button type="button" onClick={note.reload} className={cn("mt-3 px-3", CONTROL_BASE, CONTROL_OUTLINE)}>Try again</button>
          </div>
        )}

        {note.phase === "ready" && (
          <>
            {note.conflict && <ConflictNotice note={note} />}
            <div className="flex min-h-0 flex-1 flex-col px-4 pb-2 pt-3">
              <label htmlFor={editorId} className="sr-only">Your note on this paper</label>
              <textarea id={editorId} value={note.text} onChange={(e) => note.setText(e.target.value)}
                maxLength={MAX_NOTE_LENGTH} aria-describedby={hintId}
                placeholder="What do you want to remember about this paper? A question, a page, a thought."
                className="min-h-40 w-full flex-1 resize-none rounded-lg border border-stone-300 bg-white p-3 text-body leading-relaxed text-stone-900 placeholder:text-stone-500 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand" />
            </div>
            <SaveStatus note={note} />
          </>
        )}
      </div>
    </aside>
  );
}

function SaveStatus({ note }: { note: ReadingNoteState }) {
  const failed = note.status === "failed";
  const text =
    note.status === "saving" ? "Saving…"
      : note.status === "saved" ? "Saved"
        : failed ? "Could not save"
          : note.status === "conflict" ? "Not saved: choose which text to keep"
            : "";
  const nearLimit = note.text.length >= MAX_NOTE_LENGTH * 0.9;
  return (
    <div className="flex shrink-0 items-center gap-3 border-t border-stone-200 px-4 py-2 text-2xs">
      {/* A live region, always in the page, so a change of state is announced. */}
      <p role="status" className={cn("flex-1", failed ? "font-semibold text-brand" : "text-stone-600")}>
        {failed && <i className="fas fa-triangle-exclamation mr-1" aria-hidden />}{text}
      </p>
      {failed && <button type="button" onClick={note.retry} className={cn("px-3", CONTROL_BASE, CONTROL_OUTLINE)}>Try again</button>}
      {nearLimit && <span className="text-stone-600">{note.text.length.toLocaleString()} / {MAX_NOTE_LENGTH.toLocaleString()}</span>}
    </div>
  );
}

/**
 * Another device saved while this one was editing. Both texts stay on screen
 * and nothing is saved until the reader chooses (IR-580): there is no
 * invisible last-writer-wins.
 */
function ConflictNotice({ note }: { note: ReadingNoteState }) {
  const conflict = note.conflict;
  if (!conflict) return null;
  return (
    <section aria-label="Note changed on another device" className="shrink-0 border-b border-stone-200 bg-brand-50 px-4 py-3">
      <p className="text-small font-semibold text-stone-900">This note changed on another device.</p>
      <p className="mt-1 text-2xs text-stone-700">Neither text has been lost. Choose what to keep; nothing is saved until you do.</p>
      <div className="mt-2 grid gap-2 reading-split:grid-cols-2">
        <TextBlock title="Saved note" text={conflict.body} />
        <TextBlock title="On this device" text={note.text} />
      </div>
      <div className="mt-3 flex flex-wrap gap-2">
        <button type="button" onClick={note.keepBoth} className={cn("px-3", CONTROL_BASE, CONTROL_FILLED)}>Keep both</button>
        <button type="button" onClick={note.keepMine} className={cn("px-3", CONTROL_BASE, CONTROL_OUTLINE)}>Keep this device’s text</button>
        <button type="button" onClick={note.keepSaved} className={cn("px-3", CONTROL_BASE, CONTROL_OUTLINE)}>Use the saved note</button>
      </div>
    </section>
  );
}

function TextBlock({ title, text }: { title: string; text: string }) {
  return (
    <div className="min-w-0 rounded-lg border border-stone-300 bg-white p-2">
      <p className="text-3xs font-semibold uppercase tracking-wider text-stone-600">{title}</p>
      <p className="mt-1 max-h-32 overflow-y-auto whitespace-pre-wrap break-words text-2xs text-stone-900">{text || "(empty)"}</p>
    </div>
  );
}
