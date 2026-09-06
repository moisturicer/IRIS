import { useState, type FormEvent, type KeyboardEvent } from "react";

interface ChatInputProps {
  onSend:    (text: string) => void;
  disabled?: boolean;
  placeholder?: string;
}

export function ChatInput({ onSend, disabled, placeholder }: ChatInputProps) {
  const [text, setText] = useState("");

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
      className="shrink-0 border-t border-stone-200/80 bg-white px-4 sm:px-6 py-4"
    >
      <div className="flex gap-2 items-end max-w-3xl mx-auto">
        <textarea
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={handleKeyDown}
          disabled={disabled}
          rows={1}
          placeholder={placeholder ?? "Ask about the research corpus…"}
          className="flex-1 resize-none rounded-full border border-stone-200 bg-stone-50/80 px-5 py-3 text-[13px]
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
          <i className="fas fa-arrow-up text-[14px]" aria-hidden />
        </button>
      </div>
      <p className="text-[10px] text-stone-400 text-center mt-2 max-w-3xl mx-auto">
        Enter to send · Shift+Enter for new line · Verify answers using Sources
      </p>
    </form>
  );
}
