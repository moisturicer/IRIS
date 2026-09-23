import { useState } from "react";

interface CopyButtonProps {
  text:  string;
  label: string;
}

/** Copies `text` to the clipboard, with a brief "Copied" confirmation --
 *  shared by any assistant reply that wants a copy affordance. */
export function CopyButton({ text, label }: CopyButtonProps) {
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
    <button
      type="button"
      onClick={handleCopy}
      aria-label={label}
      className="inline-flex items-center gap-1.5 text-[12px] font-medium text-stone-400
        hover:text-stone-600 transition-colors duration-200"
    >
      <i className={`fas ${copied ? "fa-check" : "fa-copy"} text-[11px]`} aria-hidden />
      {copied ? "Copied" : "Copy"}
    </button>
  );
}
