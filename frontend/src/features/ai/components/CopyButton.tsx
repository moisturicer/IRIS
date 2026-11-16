import { useState } from "react";
import { cn } from "@/lib/utils";
import { COLOUR_TRANSITION, FOCUS_RING } from "@/components/ui/interaction";

/** A square, label-less action under a message; its name is its `aria-label`. */
export const MESSAGE_ACTION =
  "inline-flex size-8 shrink-0 items-center justify-center rounded-control text-stone-500 " + COLOUR_TRANSITION + " " +
  "hover:bg-stone-100 hover:text-stone-900 disabled:cursor-not-allowed disabled:opacity-40 disabled:hover:bg-transparent " +
  FOCUS_RING;

interface CopyButtonProps {
  text:  string;
  label: string;
  className?: string;
}

/** An icon that copies `text`, confirming with a check. */
export function CopyButton({ text, label, className }: CopyButtonProps) {
  const [copied, setCopied] = useState(false);

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      /* clipboard access denied -- no confirmation, nothing else to do */
    }
  };

  return (
    <button type="button" onClick={handleCopy} aria-label={label} title={copied ? "Copied" : label}
      className={cn(MESSAGE_ACTION, className)}>
      <i className={`fas ${copied ? "fa-check" : "fa-copy"} text-label`} aria-hidden />
      <span aria-live="polite" className="sr-only">{copied ? "Copied" : ""}</span>
    </button>
  );
}
