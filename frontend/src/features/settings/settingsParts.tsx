/**
 * The panel every Settings section sits in.
 *
 * Named by its title, so each panel is a landmark region. The title is
 * sentence case at a named size (DESIGN.md, the Named Size Rule).
 */
import { useId, type ReactNode } from "react";
import { TONES } from "@/components/ui/statusTones";
import { cn } from "@/lib/utils";

export function Panel({
  title, caption, children,
}: { title: string; caption: string; children: ReactNode }) {
  const titleId = useId();
  return (
    <section aria-labelledby={titleId} className="bg-white rounded-xl border border-stone-200 p-5 sm:p-6">
      <h2 id={titleId} className="text-heading font-semibold text-stone-900">{title}</h2>
      <p className="text-small text-stone-600 mt-1">{caption}</p>
      <div className="mt-5">{children}</div>
    </section>
  );
}

/** A short outcome line inside a panel: `status` for news, `alert` for a failure. */
export function Message({ tone, role, children }: { tone: "ok" | "error"; role: "status" | "alert"; children: ReactNode }) {
  return (
    <p
      role={role}
      className={cn(
        "text-[13px] rounded-lg px-3 py-2 flex items-start gap-2",
        tone === "ok" ? TONES.settled : TONES.active,
      )}
    >
      <i className={cn("fas mt-0.5 shrink-0", tone === "ok" ? "fa-check" : "fa-circle-exclamation")} aria-hidden />
      <span>{children}</span>
    </p>
  );
}
