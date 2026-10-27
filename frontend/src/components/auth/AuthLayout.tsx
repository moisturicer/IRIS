import type { ReactNode } from "react";
import { cn } from "@/lib/utils";
import { AuthBrandPanel, AuthFormBrandMark, type AuthPanelVariant } from "./AuthBrandPanel";

interface AuthLayoutProps {
  /** Which screen this is; picks the brand panel's copy (IR-535). */
  variant: AuthPanelVariant;
  children: ReactNode;
  before?: ReactNode;
  wide?: boolean;
}

/**
 * The shared frame of the entry screens: sign in and register today, email
 * verification and pending approval once they adopt it (IR-538, IR-537). The
 * brand panel already has their variants, so adopting the frame is all those
 * tickets do to it.
 *
 * It owns the one `<h1>` (IR-211); each screen's own title ("Welcome Back",
 * "Create an Account") is the `<h2>` beneath it. The heading is `sr-only`
 * rather than visible because nothing on screen is the same at every width: the
 * brand panel is desktop-only and `AuthFormBrandMark` is mobile-only, and a
 * heading inside either disappears from the accessibility tree at the other
 * size. That is how signup lost its `<h1>` on a phone when IR-208 hid the panel.
 */
export function AuthLayout({ variant, children, before, wide }: AuthLayoutProps) {
  return (
    <div className="relative flex min-h-screen flex-col bg-white font-sans lg:flex-row">
      <h1 className="sr-only">IRIS · CIT-U Research Hub</h1>
      {before}
      <AuthBrandPanel variant={variant} />
      <div
        className={cn(
          "flex flex-1 justify-center bg-white px-6 py-10 sm:px-12 lg:w-1/2 lg:px-16",
          wide ? "items-start" : "items-center",
        )}
      >
        <div className={cn("w-full", wide ? "max-w-md pb-8" : "max-w-sm")}>
          <AuthFormBrandMark />
          {children}
        </div>
      </div>
    </div>
  );
}
