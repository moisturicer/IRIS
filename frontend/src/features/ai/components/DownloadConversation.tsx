import { useState } from "react";
import { cn } from "@/lib/utils";
import { COLOUR_TRANSITION, FOCUS_RING } from "@/components/ui/interaction";
import type { ConversationFile } from "@/api/runtimeReader";
import { DownloadIcon, SpinnerIcon } from "./AskIrisIcons";

/**
 * Saves a Conversation as Markdown (IR-1167). The file comes from the runtime
 * under the reader's grant: exactly what reopening the Conversation shows.
 */
export function DownloadConversation({ download, className }: {
  download: () => Promise<ConversationFile>;
  className?: string;
}) {
  const [state, setState] = useState<"idle" | "busy" | "failed">("idle");
  const save = async () => {
    setState("busy");
    try {
      const { blob, filename } = await download();
      const url = URL.createObjectURL(blob);
      const link = Object.assign(document.createElement("a"), { href: url, download: filename });
      document.body.appendChild(link);
      link.click();
      link.remove();
      URL.revokeObjectURL(url);
      setState("idle");
    } catch {
      setState("failed");
    }
  };
  return <>
    <button type="button" onClick={() => void save()} disabled={state === "busy"}
      aria-label="Download conversation as Markdown" title="Download as Markdown"
      className={cn("relative inline-flex size-9 shrink-0 items-center justify-center rounded-control text-stone-600",
        "hover:bg-stone-100 hover:text-stone-900 disabled:cursor-wait", COLOUR_TRANSITION, FOCUS_RING, className)}>
      {state === "busy" ? <SpinnerIcon inline className="animate-spin motion-reduce:animate-none" /> : <DownloadIcon inline />}
    </button>
    {state === "failed" && <span role="alert" className="text-small text-brand-dark">Download failed. Try again.</span>}
  </>;
}
