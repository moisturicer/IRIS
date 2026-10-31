import type { ReactNode } from "react";
import { Link } from "react-router-dom";
import citLogo from "@/assets/images/cit-logo.png";
import irisLogo from "@/assets/images/iris_logo.png";
import { FOCUS_RING } from "@/components/ui/interaction";
import { cn } from "@/lib/utils";

interface CrossLink {
  /** The words before the link, shown from `sm` up ("New to IRIS?"). */
  prompt: string;
  label: string;
  to: string;
}

interface EntryLede {
  headline: ReactNode;
  sentence: string;
}

interface EntryFrameProps {
  /** The masthead's link to the other entry screen; never hidden at any width. */
  crossLink: CrossLink;
  /** Headline and plain sentence, on sign in and register only (IR-704). */
  lede?: EntryLede;
  /** The folder's index tabs, sitting on the sheet's top edge. */
  tabs: ReactNode;
  /** Rendered before the frame, for a dialog that must not sit inside it. */
  before?: ReactNode;
  children: ReactNode;
}

/**
 * The editorial entry frame, the Dossier Folder (IR-704): a masthead, an
 * optional lede, a folder whose tabs sit on a white sheet, and the CIT-U
 * footer.
 *
 * Built beside `AuthLayout` (IR-706): sign in uses it first, and the other
 * entry screens move across in IR-707 and IR-710 before IR-711 retires the
 * split frame.
 *
 * The masthead is the page's one `<h1>`, and it is visible at every width, so
 * no breakpoint can take it out of the accessibility tree as IR-211 found the
 * brand panel did. Its name is the logos' own: "IRIS" from the wordmark, the
 * university from the CIT-U logo's alt text. Both logos keep their natural
 * proportions; on a phone they are only set smaller.
 *
 * On a phone the lede's sentence follows the folder, so the email field stays
 * in the first screenful at 360x640 (IR-704 story 1). The sentence is plain
 * text, so the visual order and the reading order differing loses nothing a
 * keyboard user moves through.
 *
 * The footer carries no policy link until IR-214's documents are approved.
 */
export function EntryFrame({ crossLink, lede, tabs, before, children }: EntryFrameProps) {
  return (
    <div className="flex min-h-screen flex-col bg-canvas font-sans">
      {before}
      <header className="border-b border-stone-200 bg-white">
        <div className="mx-auto flex max-w-page items-center justify-between gap-3 px-4 py-2 sm:px-8 lg:px-12">
          <h1 className="flex min-w-0 items-center gap-2.5 sm:gap-4">
            <span className="flex shrink-0 items-center gap-2">
              <img src={irisLogo} alt="" className="size-7 sm:size-9" />
              <span className="text-heading font-extrabold tracking-widest text-brand sm:text-title">
                IRIS
              </span>
            </span>
            <span className="h-7 shrink-0 border-l border-stone-200 sm:h-9" aria-hidden />
            <img
              src={citLogo}
              alt="Cebu Institute of Technology – University"
              className="h-6 w-auto min-w-0 object-contain sm:h-9"
            />
          </h1>
          <p className="shrink-0 text-small text-stone-600">
            <span className="hidden sm:inline">{crossLink.prompt} </span>
            <Link
              to={crossLink.to}
              className={cn(
                "inline-flex min-h-11 min-w-11 items-center justify-center rounded font-semibold text-brand underline underline-offset-4 hover:text-brand-light",
                FOCUS_RING,
              )}
            >
              {crossLink.label}
            </Link>
          </p>
        </div>
      </header>

      <main className="flex flex-1 flex-col items-center px-4 pb-12 pt-section sm:px-8 sm:pt-10 lg:pt-12">
        {lede && (
          <p className="order-1 max-w-4xl text-balance font-display text-4xl font-semibold leading-tight text-stone-900 sm:text-center sm:text-5xl lg:text-6xl">
            {lede.headline}
          </p>
        )}
        {lede && (
          <p className="order-3 mt-section max-w-2xl text-pretty text-body text-stone-700 sm:text-center md:order-2 md:mt-4 md:text-lg">
            {lede.sentence}
          </p>
        )}

        {/* `isolate` keeps the second sheet behind the first without sending
            it under the page's own background. */}
        <div className="relative isolate order-2 mt-section w-full max-w-xl motion-safe:animate-sheet-settle md:order-3 md:mt-section-lg">
          <div className="relative z-10 flex gap-1 pl-4 sm:pl-5">{tabs}</div>
          <div
            className="absolute inset-x-0 bottom-0 top-11 -z-10 translate-x-2 translate-y-2 rounded-xl border border-stone-200 bg-stone-100"
            aria-hidden
          />
          <div className="rounded-xl border border-stone-200 bg-white px-5 py-8 shadow-card-md sm:px-11 sm:py-10">
            {children}
          </div>
        </div>
      </main>

      <footer className="border-t border-stone-200">
        <div className="mx-auto flex max-w-page flex-col gap-1 px-4 py-6 text-small text-stone-600 sm:flex-row sm:justify-between sm:px-8 lg:px-12">
          <p>© 2026 Cebu Institute of Technology – University</p>
          <p>IRIS · Research and IP disclosure</p>
        </div>
      </footer>
    </div>
  );
}

/**
 * A folder tab that only labels the sheet: sign in's one tab. It is not a
 * control, so it is neither a link nor a tab role. Register's stepper (IR-707)
 * brings the interactive tabs.
 */
export function FolderTab({ children }: { children: ReactNode }) {
  return (
    <span className="-mb-px rounded-t-lg border border-b-0 border-t-2 border-stone-200 border-t-brand bg-white px-5 py-3 text-small font-semibold text-brand">
      {children}
    </span>
  );
}
