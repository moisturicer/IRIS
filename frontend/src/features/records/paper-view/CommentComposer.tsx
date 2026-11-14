import { useEffect, useId, useRef, type FormEvent, type KeyboardEvent, type ReactNode } from "react";

import { CommentAvatar } from "./CommentAvatar";
import { useAutosize } from "./useAutosize";

/** Characters left at which the counter appears. Before that it is only noise. */
const SHOW_COUNTER_AT = 300;

interface CommentComposerProps {
  label: string;
  placeholder: string;
  submitLabel: string;
  value: string;
  onChange: (value: string) => void;
  onSubmit: () => void;
  /** Escape. Only a reply has one to cancel. */
  onCancel?: () => void;
  maxLength: number;
  saving: boolean;
  viewerName: string | null;
  size?: "md" | "sm";
  autoFocus?: boolean;
  /** Under the field: who is being answered and how to leave. */
  footer?: ReactNode;
}

/**
 * The field a reader writes a comment or a reply in: a rounded field with the
 * send control inside it. Enter adds a line; Ctrl or Cmd with Enter posts.
 */
export function CommentComposer({
  label,
  placeholder,
  submitLabel,
  value,
  onChange,
  onSubmit,
  onCancel,
  maxLength,
  saving,
  viewerName,
  size = "md",
  autoFocus = false,
  footer,
}: CommentComposerProps) {
  const fieldId = useId();
  const counterId = useId();
  const ref = useRef<HTMLTextAreaElement>(null);
  const remaining = maxLength - value.length;
  const canPost = value.trim().length > 0 && remaining >= 0 && !saving;

  useAutosize(ref, value);
  useEffect(() => {
    if (autoFocus) ref.current?.focus();
  }, [autoFocus]);

  const submit = (event: FormEvent) => {
    event.preventDefault();
    if (canPost) onSubmit();
  };

  const keyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === "Enter" && (event.ctrlKey || event.metaKey)) {
      event.preventDefault();
      if (canPost) onSubmit();
    } else if (event.key === "Escape" && onCancel) {
      event.preventDefault();
      onCancel();
    }
  };

  return (
    <form onSubmit={submit} className="flex items-start gap-2.5">
      <CommentAvatar name={viewerName} size={size} />
      <div className="relative min-w-0 flex-1">
        <label htmlFor={fieldId} className="sr-only">{label}</label>
        <textarea
          ref={ref}
          id={fieldId}
          value={value}
          onChange={(event) => onChange(event.target.value)}
          onKeyDown={keyDown}
          maxLength={maxLength}
          rows={1}
          placeholder={placeholder}
          aria-describedby={remaining <= SHOW_COUNTER_AT ? counterId : undefined}
          className="block max-h-64 min-h-11 w-full resize-none overflow-y-auto rounded-2xl border border-stone-300 bg-stone-100 py-2.5 pl-3.5 pr-12 text-sm text-stone-900 placeholder:text-stone-600 focus-visible:bg-surface focus-visible:outline focus-visible:outline-2 focus-visible:outline-brand reading-split:min-h-10"
        />
        <button
          type="submit"
          disabled={!canPost}
          aria-label={submitLabel}
          className="absolute bottom-0 right-0 inline-flex h-11 w-11 items-center justify-center rounded-full text-brand transition-colors duration-150 hover:bg-stone-100 focus-visible:outline focus-visible:outline-2 focus-visible:outline-brand disabled:cursor-not-allowed disabled:text-stone-500 disabled:hover:bg-transparent motion-reduce:transition-none reading-split:h-10 reading-split:w-10"
        >
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="h-4 w-4" aria-hidden="true">
            <path d="M22 2 11 13" />
            <path d="M22 2 15 22l-4-9-9-4 20-7z" />
          </svg>
        </button>
        {remaining <= SHOW_COUNTER_AT && (
          <p id={counterId} className="mt-1 text-right text-2xs text-stone-600">{remaining} characters remaining</p>
        )}
        {footer}
      </div>
    </form>
  );
}
