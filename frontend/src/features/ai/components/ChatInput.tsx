import { useState, type FormEvent, type KeyboardEvent, type ReactNode } from "react";
import { FOCUS_RING } from "@/components/ui/interaction";
import { CHAT_COLUMN, CHAT_COMPOSER_FIELD, CHAT_COMPOSER_ICON, CHAT_COMPOSER_SURFACE, CHAT_OPENING_COLUMN } from "./answerLayout";
import { AskIrisNotice } from "./AskIrisNotice";

interface ChatInputProps {
  centered?: boolean;
  onSend:    (text: string) => void;
  disabled?: boolean;
  sendDisabled?: boolean;
  children?: ReactNode;
  placeholder?: string;
  /** The box's accessible name, when the placeholder is shortened for a narrow page. */
  label?: string;
  maxLength?: number;
  /**
   * The box's text, when the page keeps it: Ask IRIS keeps one unsent draft
   * per conversation (IR-562). Never sent on its own. Without it the box
   * keeps its own text.
   */
  draft?: string;
  onDraftChange?: (text: string) => void;
}

const ATTACH_CLOSED = "Attaching files is not available yet";

export function ChatInput({ onSend, disabled, sendDisabled, children, placeholder, label, draft, onDraftChange, maxLength, centered = false }: ChatInputProps) {
  const [ownText, setOwnText] = useState("");
  const text = draft ?? ownText;
  const setText = (next: string) => (onDraftChange ? onDraftChange(next) : setOwnText(next));

  const submit = () => {
    const trimmed = text.trim();
    if (!trimmed || disabled || sendDisabled) return;
    onSend(trimmed);
    setText("");
  };

  const handleSubmit = (e: FormEvent) => {
    e.preventDefault();
    submit();
  };

  const handleKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      submit();
    }
  };

  return (
    <form
      onSubmit={handleSubmit}
      className={`shrink-0 px-4 py-3 sm:px-6 ${centered ? "" : "border-t border-stone-200/80"}`}
    >
      <div className={`grid grid-cols-[minmax(0,1fr)_auto] gap-x-2 p-1.5 ${centered ? CHAT_OPENING_COLUMN : CHAT_COLUMN} ${CHAT_COMPOSER_SURFACE}`}>
        <textarea
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={handleKeyDown}
          disabled={disabled}
          rows={1}
          maxLength={maxLength}
          aria-label={label ?? placeholder ?? "Ask about the research corpus…"}
          placeholder={placeholder ?? "Ask about the research corpus…"}
          className={`col-span-2 min-h-9 min-w-0 bg-transparent px-2.5 py-1.5 text-[15px]
            outline-none text-stone-900 placeholder:text-stone-500 disabled:opacity-50 ${CHAT_COMPOSER_FIELD}`}
        />
        <div className="col-start-1 row-start-2 flex min-w-0 flex-wrap items-center gap-1.5">
          {/* Visibly closed until uploads to a question exist. */}
          <button
            type="button"
            disabled
            title={ATTACH_CLOSED}
            aria-label={ATTACH_CLOSED}
            className={`${CHAT_COMPOSER_ICON} border border-stone-200 text-stone-400 cursor-not-allowed`}
          >
            <i className="fas fa-plus text-sm" aria-hidden />
          </button>
          {children}
        </div>
        <button
          type="submit"
          disabled={disabled || sendDisabled || !text.trim()}
          className={`${CHAT_COMPOSER_ICON} col-start-2 row-start-2 self-start bg-brand text-white
            hover:bg-brand-light disabled:bg-stone-100 disabled:text-stone-500 disabled:cursor-not-allowed
            active:scale-95 disabled:active:scale-100 motion-reduce:active:scale-100
            transition-[background-color,color,transform] duration-150 motion-reduce:transition-none ${FOCUS_RING}`}
          aria-label="Send message"
        >
          <i className="fas fa-arrow-up text-sm" aria-hidden />
        </button>
      </div>
      <AskIrisNotice className={`text-center mt-1.5 ${CHAT_COLUMN}`} />
    </form>
  );
}
