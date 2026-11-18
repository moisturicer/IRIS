/**
 * A passage of the paper the reader asks about (IR-581).
 *
 * `SelectionChip` sits over the composer: it names the paper, the Manuscript
 * version and the page, and can be removed before Send. Nothing is sent until
 * the reader presses Send, and the server checks the passage against the text
 * it has read; it never takes the browser's word for it.
 *
 * `AskedPassage` shows, above a question, the passage it was asked about, as
 * the server returns it: whole while the paper is readable, or only that it is
 * no longer available.
 */
import { cn } from "@/lib/utils";
import { FOCUS_RING } from "@/components/ui/interaction";
import type { ReaderSelection } from "@/api/runtimeReader";

export interface AskSelection {
  recordId: number;
  title: string;
  /** How the reader knows the version, e.g. "Version 3". */
  versionLabel: string;
  /** The owner's own upload, not yet submitted: Ask IRIS reads only the submitted version. */
  unsubmitted?: boolean;
  /** The `X-Manuscript-Revision` the paper was opened at; null where the server named none. */
  manuscriptRevision: string | null;
  page: number;
  quote: string;
}

/** The question a selection fills in when the reader has not started one. Editable. */
export const SELECTION_QUESTION = "What does this passage mean?";

/** What the reader is told for each refusal, and what they can do about it. */
export const SELECTION_REFUSALS: Record<string, string> = {
  selection_unverified:
    "IRIS couldn't find this text on that page of the paper it has read. Select it again, or remove it to ask without it.",
  selection_version:
    "This passage is from a different version than the one IRIS has read. Reload the paper and select it again, or remove it.",
  selection_unavailable:
    "IRIS hasn't read this paper yet, so it can't use the selection. Remove it to ask without it.",
  selection_out_of_scope: "A selection can only be asked about within this paper.",
  invalid_selection: "This selection can't be sent. Select the passage again, or remove it.",
};

/** The refusal code a failed submission names, or null when it was not about the selection. */
export function selectionRefusal(failure: unknown): string | null {
  const response = (failure as { response?: { status?: number; data?: { status?: unknown } } })?.response;
  const code = response?.status === 422 ? response.data?.status : undefined;
  return typeof code === "string" && code in SELECTION_REFUSALS ? code : null;
}

export function SelectionChip({ selection, onRemove, note }: {
  selection: AskSelection;
  onRemove: () => void;
  /** Why it will not be sent, or why it was refused. */
  note?: string;
}) {
  const where = `${selection.title} · ${selection.versionLabel} · page ${selection.page}`;
  return (
    <div role="group" aria-label={`Asking about a selection from ${where}`}
      className="rounded-card border border-stone-300 bg-white px-3 py-2 text-sm">
      <div className="flex items-start gap-2">
        <i aria-hidden className="fas fa-quote-left mt-1 text-label text-brand" />
        <div className="min-w-0 flex-1">
          <p className="break-words text-small text-stone-600">{where}</p>
          <p className="mt-0.5 break-words text-stone-800">“{selection.quote}”</p>
        </div>
        <button type="button" onClick={onRemove} aria-label="Remove selection" title="Remove selection"
          className={cn("inline-flex size-8 shrink-0 items-center justify-center rounded-control text-stone-600 hover:bg-stone-100", FOCUS_RING)}>
          <i aria-hidden className="fas fa-xmark" />
        </button>
      </div>
      {note && <p role="alert" className="mt-2 text-stone-700">{note}</p>}
    </div>
  );
}

export function AskedPassage({ selection }: { selection: ReaderSelection }) {
  if (!selection.available) {
    return <p className="text-right text-small text-stone-600">Asked about a passage that is no longer available.</p>;
  }
  return (
    // As wide as the question it sits over (ChatMessageBubble's 85%).
    <figure className="ml-auto max-w-[85%] border-l-2 border-brand/40 pl-3 text-sm text-stone-700">
      <blockquote className="break-words">“{selection.quote}”</blockquote>
      <figcaption className="mt-1 text-small text-stone-600">
        Page {selection.page}{selection.current ? "" : " · selected on an earlier version"}
      </figcaption>
    </figure>
  );
}
