import { useState, type FormEvent, type KeyboardEvent, type ReactNode } from "react";
import { FOCUS_RING } from "@/components/ui/interaction";
import { CHAT_COLUMN, CHAT_COMPOSER_FIELD, CHAT_COMPOSER_SURFACE } from "./answerLayout";
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
      className={`shrink-0 px-4 py-4 sm:px-6 ${centered ? "" : "border-t border-stone-200/80"}`}
    >
      <div className={`grid grid-cols-[minmax(0,1fr)_auto] items-end gap-x-2 p-2 ${centered ? "mx-auto w-full max-w-xl" : CHAT_COLUMN} ${CHAT_COMPOSER_SURFACE}`}>
        <textarea
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={handleKeyDown}
          disabled={disabled}
          rows={2}
          maxLength={maxLength}
          aria-label={label ?? placeholder ?? "Ask about the research corpus…"}
          placeholder={placeholder ?? "Ask about the research corpus…"}
          className={`col-span-2 min-w-0 bg-transparent px-3 py-2 text-[15px]
            outline-none text-stone-900 placeholder:text-stone-500 disabled:opacity-50 ${CHAT_COMPOSER_FIELD}`}
        />
        {children && <div className="col-start-1 row-start-2 min-w-0 self-start">{children}</div>}
        <button
          type="submit"
          disabled={disabled || sendDisabled || !text.trim()}
          className={`col-start-2 row-start-2 self-start size-11 rounded-lg bg-brand text-white flex items-center justify-center
            hover:bg-brand-light disabled:bg-stone-100 disabled:text-stone-500 disabled:cursor-not-allowed
            active:scale-95 disabled:active:scale-100 motion-reduce:active:scale-100
            transition-[background-color,color,transform] duration-150 motion-reduce:transition-none ${FOCUS_RING}`}
          aria-label="Send message"
        >
          <i className="fas fa-arrow-up text-[15px]" aria-hidden />
        </button>
      </div>
      <AskIrisNotice className={`text-center mt-1.5 ${CHAT_COLUMN}`} />
    </form>
  );
}
