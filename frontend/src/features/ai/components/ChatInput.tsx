import { useEffect, useState, type FormEvent, type KeyboardEvent } from "react";
import { CHAT_COLUMN } from "./answerLayout";
import { AskIrisNotice } from "./AskIrisNotice";

interface ChatInputProps {
  onSend:    (text: string) => void;
  disabled?: boolean;
  placeholder?: string;
  /** The box's accessible name, when the placeholder is shortened for a narrow page. */
  label?: string;
  /** Text to place in the box for the reader to edit; never sent on its own. */
  draft?: string | null;
}

export function ChatInput({ onSend, disabled, placeholder, label, draft }: ChatInputProps) {
  const [text, setText] = useState(draft ?? "");

  useEffect(() => {
    if (draft) setText(draft);
  }, [draft]);

  const submit = () => {
    const trimmed = text.trim();
    if (!trimmed || disabled) return;
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
      className="shrink-0 border-t border-stone-200/80 px-4 sm:px-6 py-4"
    >
      <div className={`flex gap-2 items-end ${CHAT_COLUMN}`}>
        <textarea
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={handleKeyDown}
          disabled={disabled}
          rows={1}
          aria-label={label ?? placeholder ?? "Ask about the research corpus…"}
          placeholder={placeholder ?? "Ask about the research corpus…"}
          className="flex-1 resize-none rounded-full border border-stone-200 bg-stone-50/80 px-5 py-3 text-[15px]
            outline-none focus:border-[#6B0F12] focus:ring-1 focus:ring-[#6B0F12] focus:bg-white
            text-stone-900 placeholder:text-stone-400 disabled:opacity-50 min-h-[48px] max-h-[120px]"
        />
        <button
          type="submit"
          disabled={disabled || !text.trim()}
          className="shrink-0 w-12 h-12 rounded-full bg-[#6B0F12] text-white flex items-center justify-center
            hover:bg-[#7d1215] disabled:opacity-40 disabled:cursor-not-allowed transition-colors shadow-sm"
          aria-label="Send message"
        >
          <i className="fas fa-arrow-up text-[15px]" aria-hidden />
        </button>
      </div>
      {/* Keyboard hints mean nothing on a touch screen, where the line would
          only push the composer up under the software keyboard (IR-570). */}
      <p className={`text-[12px] text-stone-400 text-center mt-2 [@media(pointer:coarse)]:hidden ${CHAT_COLUMN}`}>
        Enter to send · Shift+Enter for new line
      </p>
      <AskIrisNotice className={`text-center mt-1.5 ${CHAT_COLUMN}`} />
    </form>
  );
}
