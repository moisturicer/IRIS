import { cn } from "@/lib/utils";

export const ASK_IRIS_NOTICE =
  "Ask IRIS can make mistakes. Check important details against the cited papers.";

/** The persistent notice below a prompt box, in Ask IRIS and Paper Chat (IR-596). */
export function AskIrisNotice({ className }: { className?: string }) {
  return <p className={cn("text-[12px] leading-snug text-stone-500 text-pretty break-words", className)}>{ASK_IRIS_NOTICE}</p>;
}
