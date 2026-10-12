import irisLogo from "@/assets/images/iris_logo.png";
import { cn } from "@/lib/utils";

/** One per entry screen: sign in, register, verify email, await approval. */
export type AuthPanelVariant = "login" | "signup" | "verify" | "pending";

interface AuthBrandPanelProps {
  variant: AuthPanelVariant;
  className?: string;
}

/**
 * What each screen is for, in one plain sentence. Every registration, Student
 * or Adviser, creates a role request that RDCO approves after the email is
 * verified (IR-533), so the account screens say so rather than surprise anyone.
 */
const PURPOSE: Record<AuthPanelVariant, string> = {
  login: "Sign in to pick up your submissions and reviews where you left them.",
  signup:
    "Register as a student or as faculty. Once you verify your email, RDCO approves your account.",
  verify:
    "This page confirms the email address you registered with. RDCO then approves your account.",
  pending: "Your account is registered. It opens once RDCO approves it.",
};

type Binding = "brand" | "brandDark" | "brandLight" | "white";

const BINDING: Record<Binding, string> = {
  brand: "bg-brand text-white",
  brandDark: "bg-brand-dark text-brand-100",
  brandLight: "bg-brand-light text-white",
  white: "border border-b-0 border-stone-300 bg-white text-stone-900",
};

/**
 * The shelf. Spines carry only the words of the record types IRIS really holds
 * (Thesis / Research, Project, Proposal) -- never an invented title, author or
 * count. One word each, so a title fits the shortest volume. Heights are
 * fractions of the shelf, so the row shortens with the window instead of
 * pushing the copy off a short screen.
 */
const VOLUMES: ReadonlyArray<{ title: string; binding: Binding; size: string }> = [
  { title: "Thesis", binding: "brand", size: "w-14 h-5/6" },
  { title: "Project", binding: "brandDark", size: "w-14 h-4/5" },
  { title: "Proposal", binding: "white", size: "w-12 h-3/4" },
  { title: "Research", binding: "brandLight", size: "w-16 h-full" },
  { title: "Project", binding: "brand", size: "w-12 h-3/4" },
  { title: "Proposal", binding: "brandDark", size: "w-12 h-5/6" },
  { title: "Thesis", binding: "brand", size: "w-12 h-5/6" },
  { title: "Project", binding: "white", size: "w-14 h-5/6" },
  { title: "Proposal", binding: "brandLight", size: "w-10 h-3/4" },
  { title: "Research", binding: "brandDark", size: "w-14 h-full" },
  { title: "Project", binding: "brand", size: "w-11 h-4/5" },
  { title: "Proposal", binding: "white", size: "w-11 h-2/3" },
  // Enough volumes to run off the panel's edge even at 1745px: the row is cut
  // by the panel, never ended inside it. The widths above put that cut through
  // a volume, not a gap, at 1024, 1280, 1440 and 1745.
  { title: "Thesis", binding: "brandLight", size: "w-12 h-5/6" },
  { title: "Project", binding: "brandDark", size: "w-10 h-3/4" },
  { title: "Research", binding: "brand", size: "w-14 h-full" },
  { title: "Proposal", binding: "white", size: "w-12 h-4/5" },
  { title: "Thesis", binding: "brandDark", size: "w-11 h-5/6" },
  { title: "Project", binding: "brandLight", size: "w-12 h-3/4" },
];

function Shelf() {
  return (
    <div className="flex min-h-0 flex-1 flex-col justify-end" aria-hidden>
      <div className="flex h-full max-h-80 min-h-0 items-end 2xl:max-h-96 gap-1.5 pl-14 motion-safe:animate-fade-in xl:pl-20">
        {VOLUMES.map(({ title, binding, size }, i) => (
          <div
            key={i}
            className={cn(
              "relative flex shrink-0 items-center justify-center overflow-clip rounded-t-sm pt-8",
              BINDING[binding],
              size,
            )}
          >
            {/* Two gold bands at the head of each spine: decoration, nothing over them. */}
            <span className="absolute inset-x-2 top-4 border-t-2 border-gold/80" />
            <span className="absolute inset-x-2 top-6 border-t-2 border-gold/80" />
            {/* On a short window the shortest spines fall under ~80px and a
                centred title would climb into the bands, so titles go. */}
            <span className="text-spine whitespace-nowrap font-display text-title font-semibold short:hidden">
              {title}
            </span>
          </div>
        ))}
      </div>
      <div className="h-3.5 shrink-0 bg-stone-300" />
    </div>
  );
}

/** Logo and wordmark, with the line beneath it. The wordmark is a logotype, set in Inter. */
function Lockup({ tagline, size }: { tagline: string; size: "panel" | "phone" }) {
  return (
    <div className="flex items-center gap-3.5">
      <span
        className={cn(
          "flex shrink-0 items-center justify-center rounded-lg border border-stone-200 bg-white p-1.5",
          size === "panel" ? "size-11" : "size-12",
        )}
      >
        <img src={irisLogo} alt="" className="size-full object-contain" />
      </span>
      <span className="flex flex-col">
        <span className="text-title font-extrabold leading-none tracking-widest text-brand">IRIS</span>
        <span className={cn("mt-1", size === "panel" ? "text-small text-stone-700" : "text-label text-stone-600")}>
          {tagline}
        </span>
      </span>
    </div>
  );
}

/**
 * The entry screens' brand panel (IR-535): what IRIS is, what this screen is
 * for, and a shelf of the university's bound work.
 *
 * Every line is true and plain. It carries no quotation, no figure and no claim
 * of prestige: "1,200+ Registered Assets" went in IR-206, and the design-brief
 * quotation and "a prestigious archive" went here. A live count would need an
 * unauthenticated aggregate endpoint, which is a visibility decision, not a
 * design one.
 *
 * Desktop only. Below `lg` it stacked above the form and pushed the first field
 * under the fold on every phone (IR-208); `AuthFormBrandMark` is the phone's
 * branding. It holds no heading: a heading here would vanish below `lg`, and
 * `AuthLayout` owns the one `<h1>` (IR-211).
 *
 * Contrast on `stone-100`: `stone-900` 16.0:1, `stone-700` 9.4:1, `brand`
 * 11.3:1, `stone-600` 7.0:1. Spine titles: white on `brand` 12.3:1, `brand-100`
 * on `brand-dark` 13.0:1, white on `brand-light` 9.5:1, `stone-900` on white
 * 17.5:1. Gold appears only as the bands on the spines, never as text or behind
 * it (2.8:1 on white).
 *
 * The statement is set at `text-4xl`/`2xl:text-5xl` in `font-display`, as a
 * paper's title is, rather than at the `display` role's 28px: it is the one
 * line this screen exists to say (01-design-system, IR-535 amendment).
 */
export function AuthBrandPanel({ variant, className }: AuthBrandPanelProps) {
  return (
    <aside
      aria-label="About IRIS"
      className={cn("relative hidden overflow-clip bg-stone-100 lg:flex lg:w-1/2", className)}
    >
      {/* Sticky, so on the long register form the panel stays in view while
          the form scrolls past it. `overflow-clip` rather than `-hidden`: a
          hidden overflow would make this the scroll container and pin nothing. */}
      <div className="flex w-full flex-col lg:sticky lg:top-0 lg:h-screen">
        <div className="px-14 pt-12 xl:px-20 xl:pt-16">
          <Lockup tagline="Cebu Institute of Technology – University" size="panel" />

          <p className="mt-section-lg max-w-xl text-balance font-display text-4xl font-semibold leading-tight text-stone-900 xl:mt-12 2xl:text-5xl 2xl:leading-tight">
            CIT-U theses, projects and proposals, <span className="text-brand">on one shelf.</span>
          </p>
          <p className="mt-4 max-w-lg text-pretty text-body text-stone-700">
            IRIS is the university&apos;s research and IP disclosure system. Work is submitted here and
            reviewed by an adviser and the university&apos;s offices; theses and projects that clear
            review are published to Discover.
          </p>
          <p className="mt-section max-w-lg border-t border-stone-300 pt-section text-balance text-heading font-medium text-stone-900">
            {PURPOSE[variant]}
          </p>
        </div>

        <div className="mt-section-lg flex min-h-0 flex-1 flex-col">
          <Shelf />
          <p className="shrink-0 px-14 py-4 text-small text-stone-600 xl:px-20">
            © 2026 Cebu Institute of Technology – University
          </p>
        </div>
      </div>
    </aside>
  );
}

/** Compact lockup for the form column below `lg`, where the panel is hidden (IR-208). */
export function AuthFormBrandMark() {
  return (
    <div className="mb-8 border-b border-stone-200 pb-6 lg:hidden">
      <Lockup tagline="CIT-U research and IP disclosure" size="phone" />
    </div>
  );
}
