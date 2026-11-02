/**
 * The panel every Settings & Profile section sits in, shared so the profile
 * fields (IR-699) sit in the same frame as the panels already there.
 *
 * Named by its title, so each panel is a landmark region. The title is
 * sentence case at a named size (DESIGN.md, the Named Size Rule); it was
 * small tracked capitals before IR-699.
 */
import { useId, type ReactNode } from "react";

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
