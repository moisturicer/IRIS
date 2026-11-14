import { useMediaQuery } from "@/hooks/useMediaQuery";

/**
 * The app shell's three sidebar shapes (IR-1086, spec §4.7):
 *
 * - `drawer`  below 768 px: hidden, opened over the page from the phone bar.
 * - `rail`    768-1023 px: the 76 px icon rail, always on screen. The IRIS mark
 *             opens the full sidebar *over* the page, so the content is never
 *             squeezed (audit NAV-06).
 * - `desktop` from 1024 px: the full sidebar, or the rail if the reader chose it.
 *
 * Widths live in Tailwind (`w-rail` is 76 px in `tailwind.config.js`, `w-60` is
 * 240 px, `md` and `lg` are 768 and 1024 px); only behaviour that has to follow
 * a breakpoint reads the queries below, and they must match those classes.
 */
const PHONE_QUERY = "(max-width: 767.98px)";
const TABLET_QUERY = "(min-width: 768px) and (max-width: 1023.98px)";

export type SidebarMode = "drawer" | "rail" | "desktop";

/**
 * Which shape the sidebar has at this window width. `desktop` wherever
 * `matchMedia` does not exist (jsdom).
 */
export function useSidebarMode(): SidebarMode {
  const phone = useMediaQuery(PHONE_QUERY);
  const tablet = useMediaQuery(TABLET_QUERY);
  if (phone) return "drawer";
  return tablet ? "rail" : "desktop";
}

/**
 * Whether the sidebar is drawn as the icon rail right now.
 *
 * On a tablet the rail is the resting state and the full sidebar is open only
 * while the reader has opened it; the saved collapse preference is for the
 * desktop and is neither read nor written there.
 */
export function isRail(mode: SidebarMode, open: boolean, preferCollapsed: boolean): boolean {
  if (mode === "drawer") return false;
  if (mode === "rail") return !open;
  return preferCollapsed;
}
