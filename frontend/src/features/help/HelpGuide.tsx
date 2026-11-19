import { useEffect } from "react";
import { useLocation } from "react-router-dom";

import { FOCUS_RING } from "@/components/ui/interaction";
import { cn } from "@/lib/utils";
import { useAuthStore } from "@/store/auth.store";

import { sectionsFor } from "./helpSections";

/**
 * Help (IR-745): a contents list, and a section per task.
 *
 * Settings' Help section since IR-1245, at `/settings?tab=help`; it was a page
 * of its own at `/help`, which now redirects here, keeping the fragment.
 *
 * A reader sees only the sections for screens they can open, decided by the
 * same rules as the sidebar. Each section has a stable anchor, so another
 * screen can link straight to it (`/settings?tab=help#ask-iris`).
 */
export function HelpGuide() {
  const user = useAuthStore((s) => s.user);
  const sections = sectionsFor({ role: user?.role_name, reviewAccess: user?.review_access, canAuthor: user?.can_author });
  const { hash } = useLocation();

  // The router does not scroll to a fragment on a client-side navigation.
  useEffect(() => {
    if (!hash) return;
    document.getElementById(decodeURIComponent(hash.slice(1)))?.scrollIntoView?.();
  }, [hash]);

  return (
    // Two columns only where Settings' content column leaves room for both
    // the contents and a readable measure (IR-1245).
    <div className="xl:grid xl:grid-cols-[12rem_minmax(0,68ch)] xl:gap-8">
      <nav aria-label="Help contents" className="mb-section-lg xl:sticky xl:top-6 xl:mb-0 xl:self-start">
        <h3 className="px-3 text-label font-semibold text-stone-500">On this page</h3>
        <ul className="mt-1 flex flex-wrap gap-x-1 xl:grid xl:gap-0.5">
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

      <div className="min-w-0">
        {sections.map((s) => (
          <section key={s.id} id={s.id} aria-labelledby={`${s.id}-title`} className="scroll-mt-6 pb-section-lg">
            <h3 id={`${s.id}-title`} className="mb-3 font-display text-section font-semibold text-stone-900">
              {s.title}
            </h3>
            <div className="text-body leading-[1.75] text-stone-700 [&_p]:text-justified [&_li]:mt-1 [&_li]:marker:text-brand [&_p+p]:mt-4 [&_ul]:my-3 [&_ul]:list-disc [&_ul]:pl-5">
              {s.body}
            </div>
          </section>
        ))}
      </div>
    </div>
  );
}
