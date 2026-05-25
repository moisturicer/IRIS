import type { ReactNode } from "react";
import { AuthBrandPanel, AuthFormBrandMark } from "./AuthBrandPanel";

interface AuthLayoutProps {
  variant: "login" | "signup";
  children: ReactNode;
  before?: ReactNode;
  wide?: boolean;
}

export function AuthLayout({ variant, children, before, wide }: AuthLayoutProps) {
  return (
    <div className="min-h-screen flex flex-col lg:flex-row font-sans relative">
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
