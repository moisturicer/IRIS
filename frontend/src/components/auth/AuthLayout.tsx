import type { ReactNode } from "react";
import { AuthBrandPanel, AuthFormBrandMark } from "./AuthBrandPanel";

interface AuthLayoutProps {
  variant: "login" | "signup";
  children: ReactNode;
  /** Extra nodes rendered before children (e.g. modals). */
  before?: ReactNode;
}

export function AuthLayout({ variant, children, before }: AuthLayoutProps) {
  return (
    <div className="min-h-screen flex flex-col lg:flex-row font-sans relative">
      {before}
      <AuthBrandPanel variant={variant} />
      <div className="flex-1 lg:w-1/2 bg-white flex items-center justify-center px-8 py-10 sm:px-12 lg:px-16">
        <div className="w-full max-w-[400px]">
          <AuthFormBrandMark />
          {children}
        </div>
      </div>
    </div>
  );
}
