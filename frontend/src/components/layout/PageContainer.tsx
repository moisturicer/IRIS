import type { ReactNode } from "react";

import { cn } from "@/lib/utils";

/**
 * How wide an app page may grow (IR-519, IR-521).
 *
 * Pages used to stop at whatever cap each one picked -- 1152px (Paper View,
 * Discover), 1200px (Settings), 1400px (Calls & Conferences) or none -- so at
 * 90% zoom, which a 1920px screen draws as a ~2130px-wide window, most sat in
 * a narrow column between wide margins. This is now the one cap.
 *
 * - **standard**: centred, up to 1440px. Extra width goes to the layout --
 *   wider rails and cards -- while running text keeps its own reading measure
 *   (`max-w-prose`), so a wide page never means long lines.
 * - **full**: the whole width, for the PDF reader and wide tables.
 *
 * Not fluid scaling: that would cancel browser zoom (WCAG 1.4.4).
 */
export type PageWidth = "standard" | "full";

/** Whole class strings, because Tailwind only generates what it finds written out. */
export const PAGE_WIDTH: Record<PageWidth, string> = {
  standard: "w-full max-w-[90rem] mx-auto",
  full: "w-full",
};

interface PageContainerProps {
  width?: PageWidth;
  className?: string;
  children: ReactNode;
}

export function PageContainer({ width = "standard", className, children }: PageContainerProps) {
  return <div className={cn(PAGE_WIDTH[width], className)}>{children}</div>;
}
