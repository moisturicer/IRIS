import type { ReactNode } from "react";
import { AuthBrandPanel, AuthFormBrandMark } from "./AuthBrandPanel";

interface AuthLayoutProps {
  variant: "login" | "signup";
  children: ReactNode;
  before?: ReactNode;
  wide?: boolean;
}

/**
 * The shared frame of the login and signup screens. Email verification still
 * draws its own and carries its own `<h1>` until it joins this one (IR-213).
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
    <div className="min-h-screen flex flex-col lg:flex-row font-sans relative">
      <h1 className="sr-only">IRIS · CIT-U Research Hub</h1>
      {before}
      <AuthBrandPanel variant={variant} />
      <div
        className={`flex-1 lg:w-1/2 bg-white flex justify-center px-8 py-10 sm:px-12 lg:px-16 ${
          wide ? "items-start overflow-y-auto" : "items-center"
        }`}
      >
        <div className={`w-full ${wide ? "max-w-[480px] pb-8" : "max-w-[400px]"}`}>
          <AuthFormBrandMark />
          {children}
        </div>
      </div>
    </div>
  );
}
