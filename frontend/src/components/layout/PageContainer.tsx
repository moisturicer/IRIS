import type { ReactNode } from "react";

import { cn } from "@/lib/utils";

/**
 * The page frame: one margin and one width for every page (IR-519, IR-521, IR-1353).
 *
 * Pages used to stop at whatever cap each one picked -- 1152px (Paper View,
 * Discover), 1200px (Settings), 1400px (Calls & Conferences) or none -- so at
 * 90% zoom, which a 1920px screen draws as a ~2130px-wide window, most sat in
 * a narrow column between wide margins. IR-521 made the cap one value. IR-1353
 * made the margin one value too: the admin tables ran edge to edge, Discover
 * put its padding inside the cap instead of outside it, and the record
 * Overview kept its own 56px left gutter, so moving between pages moved the
 * content sideways.
 *
 * The frame is the gutter outside, the cap inside. A page sets neither, and a
 * wide table scrolls inside its own box instead of widening the page. Ask
 * IRIS, the PDF reader and the review workspace are the only pages outside
 * it: they are workspaces that fill the window.
 *
 * Not fluid scaling: that would cancel browser zoom (WCAG 1.4.4).
 */

/** The margin around a page: 16px on a phone and 28px from 640px, on every side. */
export const PAGE_GUTTER = "p-4 sm:p-7";

/**
 * - **standard**: centred, up to 1440px. Extra width goes to the layout --
 *   wider rails and cards -- while running text keeps its own reading measure
 *   (`max-w-prose`), so a wide page never means long lines.
 * - **wide-left**: centred, up to 1600px, for the record Overview only, which
 *   pins a rail to the right edge of its own box (IR-1144): the gap between
 *   page and rail stops growing past the cap, and a wide window splits its
 *   spare room evenly on both sides. Its owner kept this width in IR-1353. It
 *   starts at the standard page's x until a window is wide enough for the
 *   1440px cap to bind, and up to 80px further left past that.
 *
 * Whole class strings, because Tailwind only generates what it finds written out.
 */
export type PageWidth = "standard" | "wide-left";

export const PAGE_WIDTH: Record<PageWidth, string> = {
  standard: "w-full max-w-page mx-auto",
  "wide-left": "w-full max-w-[100rem] mx-auto",
};

interface PageContainerProps {
  className?: string;
  children: ReactNode;
}

/** The frame `AppShell` draws around every page: the gutter, then the standard width. */
export function PageContainer({ className, children }: PageContainerProps) {
  return (
    <div className={PAGE_GUTTER}>
      <div className={cn(PAGE_WIDTH.standard, className)}>{children}</div>
    </div>
  );
}
