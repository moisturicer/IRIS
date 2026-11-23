import { useEffect, useRef, useState, type KeyboardEvent } from "react";
import { COLOUR_TRANSITION, FOCUS_RING } from "@/components/ui/interaction";
import { cn } from "@/lib/utils";

/**
 * The question edited where it was asked (IR-1306). Enter sends the edited
 * question in place of the old one; Shift+Enter is a new line; Escape keeps the
 * question as it was.
 */
export function EditQuestion({ question, onCancel, onSend, compact = false }: {
  question: string;
  onCancel: () => void;
  onSend: (question: string) => void;
  compact?: boolean;
}) {
  const [text, setText] = useState(question);
  const field = useRef<HTMLTextAreaElement>(null);
  useEffect(() => {
    const el = field.current;
    if (!el) return;
    el.focus();
    el.setSelectionRange(el.value.length, el.value.length);
  }, []);
  const ready = text.trim().length > 0;
  const submit = () => { if (ready) onSend(text.trim()); };
  const onKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) { e.preventDefault(); submit(); }
    else if (e.key === "Escape") { e.preventDefault(); onCancel(); }
  };
  return (
    <div className="flex justify-end">
      <div className={cn("w-full rounded-card border border-brand/40 bg-surface p-2 ring-4 ring-brand/10", compact ? "max-w-full" : "max-w-[85%]")}>
        <textarea ref={field} value={text} onChange={e => setText(e.target.value)} onKeyDown={onKeyDown}
          aria-label="Edit your question" rows={2} maxLength={4000}
          className="block max-h-48 min-h-[3rem] w-full resize-none bg-transparent px-2 py-1 text-body text-stone-900 caret-brand outline-none [field-sizing:content]" />
        <div className="mt-1 flex items-center justify-end gap-2">
          <span className="mr-auto px-2 text-label text-stone-500">Enter to send · Esc to cancel</span>
          <button type="button" onClick={onCancel}
            className={cn("min-h-9 rounded-full px-3.5 text-small font-medium text-stone-700 hover:bg-brand/[0.07] hover:text-brand-dark", COLOUR_TRANSITION, FOCUS_RING)}>
            Cancel
          </button>
          <button type="button" onClick={submit} disabled={!ready}
            className={cn("min-h-9 rounded-full bg-brand px-4 text-small font-semibold text-white hover:bg-brand-light disabled:bg-stone-200 disabled:text-stone-500", COLOUR_TRANSITION, FOCUS_RING)}>
            Send
          </button>
        </div>
      </div>
    </div>
  );
}
