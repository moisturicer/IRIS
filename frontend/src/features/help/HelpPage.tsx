import { useEffect } from "react";
import { useLocation } from "react-router-dom";

import { PageHeader } from "@/components/layout/PageHeader";
import { FOCUS_RING } from "@/components/ui/interaction";
import { cn } from "@/lib/utils";
import { useAuthStore } from "@/store/auth.store";

import { sectionsFor } from "./helpSections";

/**
 * Help (IR-745): one page, a contents list, and a section per task.
 *
 * A reader sees only the sections for screens they can open, decided by the
 * same rules as the sidebar. Each section has a stable anchor, so another
 * screen can link straight to it (`/help#ask-iris`).
 */
export default function HelpPage() {
  const user = useAuthStore((s) => s.user);
  const sections = sectionsFor({ role: user?.role_name, reviewAccess: user?.review_access });
  const { hash } = useLocation();

  // The router does not scroll to a fragment on a client-side navigation.
  useEffect(() => {
    if (!hash) return;
    document.getElementById(decodeURIComponent(hash.slice(1)))?.scrollIntoView?.();
  }, [hash]);

  return (
    <div>
      <PageHeader title="Help" description="How to find, publish and review research in IRIS." />

      <nav aria-label="Help contents" className="mb-section-lg rounded-xl border border-stone-200 bg-surface p-card">
        <h2 className="text-label font-semibold uppercase tracking-wide text-stone-500">Contents</h2>
        <ul className="mt-2 grid gap-1 sm:grid-cols-2">
          {sections.map((s) => (
            <li key={s.id}>
              <a href={`#${s.id}`} className={cn("rounded text-small font-medium text-brand hover:underline", FOCUS_RING)}>
                {s.title}
              </a>
            </li>
          ))}
        </ul>
      </nav>

      <div className="space-y-section-lg">
        {sections.map((s) => (
          <section key={s.id} id={s.id} aria-labelledby={`${s.id}-title`} className="scroll-mt-6">
            <h2 id={`${s.id}-title`} className="font-display text-title font-semibold text-stone-900">
              {s.title}
            </h2>
            <div className="mt-2 max-w-prose space-y-3 text-body text-stone-700 [&_li]:mt-1 [&_ul]:list-disc [&_ul]:pl-5">
              {s.body}
            </div>
          </section>
        ))}
      </div>
    </div>
  );
}
