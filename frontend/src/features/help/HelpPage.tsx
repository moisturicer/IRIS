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
  const sections = sectionsFor({ role: user?.role_name, reviewAccess: user?.review_access, canAuthor: user?.can_author });
  const { hash } = useLocation();

  // The router does not scroll to a fragment on a client-side navigation.
  useEffect(() => {
    if (!hash) return;
    document.getElementById(decodeURIComponent(hash.slice(1)))?.scrollIntoView?.();
  }, [hash]);

  return (
    <div>
      <PageHeader title="Help" description="How to find, publish and review research in IRIS." />

      <div className="lg:grid lg:grid-cols-[13.75rem_minmax(0,68ch)] lg:gap-10">
        <nav aria-label="Help contents" className="mb-section-lg lg:sticky lg:top-6 lg:mb-0 lg:self-start">
          <h2 className="px-3 text-label font-semibold text-stone-500">On this page</h2>
          <ul className="mt-1 flex flex-wrap gap-x-1 lg:grid lg:gap-0.5">
            {sections.map((s) => (
              <li key={s.id}>
                <a
                  href={`#${s.id}`}
                  className={cn(
                    "block rounded-control px-3 py-2 text-body text-stone-700 hover:bg-stone-100 hover:text-brand",
                    FOCUS_RING,
                  )}
                >
                  {s.title}
                </a>
              </li>
            ))}
          </ul>
        </nav>

        <div>
          {sections.map((s) => (
            <section key={s.id} id={s.id} aria-labelledby={`${s.id}-title`} className="scroll-mt-6 pb-section-lg">
              <h2 id={`${s.id}-title`} className="mb-3 font-display text-section font-semibold text-stone-900">
                {s.title}
              </h2>
              <div className="text-body leading-[1.75] text-stone-700 [&_p]:text-reading [&_li]:mt-1 [&_li]:marker:text-brand [&_p+p]:mt-4 [&_ul]:my-3 [&_ul]:list-disc [&_ul]:pl-5">
                {s.body}
              </div>
            </section>
          ))}
        </div>
      </div>
    </div>
  );
}
