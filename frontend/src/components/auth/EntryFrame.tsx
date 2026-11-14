import { useState, type ReactNode } from "react";
import { Link } from "react-router-dom";
import { Modal } from "@/components/ui/Modal";
import { Button } from "@/components/ui/Button";
import { DataNotice } from "@/features/auth/DataNotice";
import { IrisMark, IrisWordmark } from "@/components/brand/IrisBrand";
import { FOCUS_RING } from "@/components/ui/interaction";
import { INSTITUTION } from "@/config/institution";
import { cn } from "@/lib/utils";

interface EntryLede {
  headline: ReactNode;
  sentence: string;
}

interface EntryFrameProps {
  /** Account help on sign in and register, without leaving the form. */
  help?: boolean;
  /** Headline and plain sentence, on sign in and register only (IR-704). */
  lede?: EntryLede;
  /** The folder's index tabs, sitting on the sheet's top edge. */
  tabs: ReactNode;
  /** Rendered before the frame, for a dialog that must not sit inside it. */
  before?: ReactNode;
  /** A wider sheet, for register's two columns (IR-707). */
  wide?: boolean;
  children: ReactNode;
}

/**
 * The editorial entry frame, the Dossier Folder (IR-704): a masthead, an
 * optional lede, a folder whose tabs sit on a white sheet, and the
 * footer naming IRIS and linking to privacy and terms (IR-769).
 *
 * Sign in moved onto it first (IR-706), register in IR-707, and email
 * verification and the pending and declined screens without the lede in
 * IR-710. It is the only entry frame: IR-711 deleted the split frame
 * (`AuthLayout` and its brand panel).
 *
 * The page's one `<h1>` is visible at every width, so no breakpoint can take
 * it out of the accessibility tree as IR-211 found the brand panel did. On a
 * screen with a lede it is the headline (IR-1093) and the masthead is a plain
 * container; on one without, it is the masthead, whose name is the logos' own.
 * Either way the masthead names the system: "IRIS" from the wordmark, the
 * institution from its logo's alt text, read from `config/institution`
 * (IR-768). Both logos keep their natural proportions; on a phone they are only set smaller.
 *
 * On a phone the lede's sentence follows the folder, so the email field stays
 * in the first screenful at 360x640 (IR-704 story 1). The sentence is plain
 * text, so the visual order and the reading order differing loses nothing a
 * keyboard user moves through.
 *
 * Policy dialogs identify interim material; approval remains with IR-214.
 */
export function EntryFrame({ help, lede, tabs, before, wide, children }: EntryFrameProps) {
  const [information, setInformation] = useState<"Help" | "Data privacy" | "Terms" | null>(null);
  const informationLink = (label: "Help" | "Data privacy" | "Terms", fragment: string) => (
    <a
      href={`#${fragment}`}
      aria-haspopup="dialog"
      onClick={(event) => { event.preventDefault(); setInformation(label); }}
      className={cn(
        "inline-flex min-h-11 min-w-11 items-center justify-center rounded font-semibold text-brand underline underline-offset-4 hover:text-brand-light",
        FOCUS_RING,
      )}
    >
      {label}
    </a>
  );
  // The page's one `<h1>` is its visible headline when it has one (IR-1093);
  // a screen without a lede (verification, pending) keeps the masthead, whose
  // name is the logos' own.
  const Masthead = lede ? "div" : "h1";
  return (
    <div className="flex min-h-screen flex-col bg-canvas font-sans">
      {before}
      <Modal
        open={information !== null}
        onClose={() => setInformation(null)}
        title={information ?? undefined}
        footer={<Button variant="outline" size="full" onClick={() => setInformation(null)}>Close dialog</Button>}
      >
        {information === "Data privacy" && <DataNotice />}
        {information === "Terms" && (
          <p className="text-small text-stone-700">
            Terms of Service are pending institutional review. Approved terms have
            not yet been published. The data notice, under Data privacy, describes how IRIS
            uses your details.
          </p>
        )}
        {information === "Help" && (
          <div className="space-y-3 text-small text-stone-700">
            <p>Sign in with your registered email address and password.</p>
            <p>To join IRIS, choose Create an account, complete your details, and verify your email.
              An administrator reviews your role request before you can access the workspace.</p>
            <Link to="/password/forgot" className={cn("inline-flex min-h-11 items-center rounded font-semibold text-brand underline", FOCUS_RING)}>
              Reset your password
            </Link>
          </div>
        )}
      </Modal>
      <header className="border-b border-stone-200 bg-white">
        <div className="mx-auto flex max-w-page items-center justify-between gap-3 px-4 py-2 sm:px-8 lg:px-12">
          <Masthead className="flex min-w-0 items-center gap-2.5 sm:gap-4">
            <span className="flex shrink-0 items-center gap-2">
              <IrisMark className="size-7 text-brand sm:size-9" />
              <span className="text-brand">
                <IrisWordmark className="h-3.5 w-auto sm:h-4" />
                <span className="sr-only">IRIS</span>
              </span>
            </span>
            <span className="h-7 shrink-0 border-l border-stone-200 sm:h-9" aria-hidden />
            <img
              src={INSTITUTION.logo}
              alt={INSTITUTION.name}
              className="h-6 w-auto min-w-0 object-contain sm:h-9"
            />
          </Masthead>
          {help && <div className="shrink-0 text-small">{informationLink("Help", "entry-help")}</div>}
        </div>
      </header>

      <main className="flex flex-1 flex-col items-center px-4 pb-12 pt-section sm:px-8 sm:pt-10 lg:pt-12">
        {lede && (
          <h1 className="order-1 max-w-4xl text-balance font-display text-4xl font-semibold leading-tight text-stone-900 sm:text-5xl md:text-center lg:text-6xl">
            {lede.headline}
          </h1>
        )}
        {lede && (
          <p className="order-3 mt-section max-w-2xl text-pretty text-body text-stone-700 md:order-2 md:text-center md:mt-4 md:text-lg">
            {lede.sentence}
          </p>
        )}

        {/* `isolate` keeps the second sheet behind the first without sending
            it under the page's own background. */}
        <div
          className={cn(
            "relative isolate order-2 mt-section w-full motion-safe:animate-sheet-settle md:order-3 md:mt-section-lg",
            wide ? "max-w-5xl" : "max-w-xl",
          )}
        >
          <div className="relative z-10 flex gap-1">{tabs}</div>
          <div
            className="absolute inset-x-0 bottom-0 top-11 -z-10 translate-x-2 translate-y-2 rounded-xl border border-stone-200 bg-stone-100"
            aria-hidden
          />
          <div className="rounded-b-xl rounded-tr-xl border border-stone-200 bg-white px-5 py-8 shadow-card-md sm:px-11 sm:py-10">
            {children}
          </div>
        </div>
      </main>

      <footer className="border-t border-stone-200">
        <div className="mx-auto flex max-w-page flex-col gap-1 px-4 py-6 text-small text-stone-600 sm:flex-row sm:justify-between sm:px-8 lg:px-12">
          <nav aria-label="Privacy and terms" className="flex flex-wrap gap-x-5">
            {informationLink("Data privacy", "data-privacy")}
            {informationLink("Terms", "terms")}
          </nav>
          <p>© 2026 IRIS · Research and IP disclosure</p>
        </div>
      </footer>
    </div>
  );
}

/**
 * A tab on the entry folder that only labels the sheet: the one tab of sign
 * in, email verification and the pending screen.
 * Not named for the domain's Folder, which is a reader's group of Saved
 * Records (CONTEXT.md). It is not a
 * control, so it is neither a link nor a tab role. Register's stepper is
 * `EntrySteps` (IR-707).
 */
export function EntryTab({ children }: { children: ReactNode }) {
  return (
    <span className="entry-label -mb-px rounded-tl-xl rounded-tr-xl border border-b-0 border-t-2 border-stone-200 border-t-brand bg-white px-5 py-3 text-small font-semibold text-brand">
      {children}
    </span>
  );
}
