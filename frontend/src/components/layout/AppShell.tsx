import { forwardRef, useCallback, useEffect, useRef } from "react";
import { Outlet, useLocation, useMatches } from "react-router-dom";
import { Sidebar } from "./Sidebar";
import { Breadcrumbs, type RouteHandle } from "./Breadcrumbs";
import { NotificationBell } from "./NotificationBell";
import { PageContainer } from "./PageContainer";
import { Button } from "@/components/ui/Button";
import { FOCUS_RING } from "@/components/ui/interaction";
import { useUIStore } from "@/store/ui.store";
import { useAuth } from "@/hooks/useAuth";
import { useMediaQuery } from "@/hooks/useMediaQuery";
import { PendingApprovalPage } from "@/features/auth/PendingApprovalPage";
import { cn } from "@/lib/utils";

/**
 * The menu button and the bell, for phones (IR-519).
 *
 * There is no app header any more: on a desktop the bell sits at the top of
 * the sidebar, which is always on screen. Below `md` the sidebar is a hidden
 * drawer, so this bar carries the two things that would otherwise be out of
 * reach. It scrolls away with the page rather than sticking, so it costs no
 * height once the reader is past it -- and no sticky offset depends on it.
 */
const PhoneBar = forwardRef<HTMLButtonElement>(function PhoneBar(_props, menuButtonRef) {
  const toggleSidebar = useUIStore((s) => s.toggleSidebar);
  const sidebarOpen = useUIStore((s) => s.sidebarOpen);
  return (
    <nav
      aria-label="Menu"
      className="md:hidden flex items-center justify-between gap-3 h-14 px-4 bg-surface border-b border-stone-200"
    >
      <Button
        ref={menuButtonRef}
        type="button"
        variant="outline"
        size="icon"
        onClick={toggleSidebar}
        aria-label="Open menu"
        aria-expanded={sidebarOpen}
        aria-controls="app-sidebar"
        className={FOCUS_RING}
      >
        <i className="fas fa-bars text-base" aria-hidden />
      </Button>
      <NotificationBell />
    </nav>
  );
});

export function AppShell() {
  const sidebarOpen  = useUIStore((s) => s.sidebarOpen);
  const collapsed    = useUIStore((s) => s.sidebarCollapsed);
  const closeSidebar = useUIStore((s) => s.closeSidebar);
  const { pathname } = useLocation();
  // Routes that paint their own page and manage their own scrolling.
  const isFullBleed = pathname === "/" || pathname === "/ai";
  // Ask IRIS fills the window exactly (`h-screen`) and its toolbar carries the
  // bell on a phone, so a bar above it would push the composer off screen.
  const showPhoneBar = pathname !== "/ai";
  // The deepest route that names a width wins; a page is standard otherwise.
  const matches = useMatches();
  const width = [...matches].reverse()
    .map((m) => (m.handle as RouteHandle | undefined)?.width)
    .find(Boolean) ?? "standard";

  // Below md the sidebar is a drawer over the page (IR-413). While it is
  // closed it is only slid off screen, so it is made inert to keep its links
  // out of the tab order; while it is open the page behind it is inert
  // instead, Escape closes it, and focus moves in and back out again.
  // `max-width` so jsdom, which has no matchMedia, renders the desktop shell.
  const isPhone = useMediaQuery("(max-width: 767.98px)");
  const drawerOpen = isPhone && sidebarOpen;
  const sidebarRef = useRef<HTMLElement>(null);
  const menuButtonRef = useRef<HTMLButtonElement>(null);
  // Set only when the reader dismissed the drawer (Escape, Close menu, the
  // backdrop). Choosing a link also closes it, and then focus belongs to the
  // page that opened, not to Open menu -- which Ask IRIS does not even render.
  const returnFocus = useRef(false);
  const dismiss = useCallback(() => {
    returnFocus.current = true;
    closeSidebar();
  }, [closeSidebar]);

  useEffect(() => {
    if (drawerOpen) {
      sidebarRef.current?.querySelector<HTMLElement>("[data-drawer-focus]")?.focus();
      const onKeyDown = (e: KeyboardEvent) => {
        if (e.key === "Escape") dismiss();
      };
      document.addEventListener("keydown", onKeyDown);
      return () => document.removeEventListener("keydown", onKeyDown);
    }
    if (returnFocus.current) {
      returnFocus.current = false;
      menuButtonRef.current?.focus();
    }
  }, [drawerOpen, dismiss]);

  // Widening past md leaves no drawer to be open. Closing it means it cannot
  // reopen, and take focus, if the window narrows again.
  useEffect(() => {
    if (!isPhone && sidebarOpen) closeSidebar();
  }, [isPhone, sidebarOpen, closeSidebar]);

  const { user } = useAuth();
  // Block users who are logged in but whose role request hasn't been approved yet.
  // Django staff/superuser accounts (no role) are exempt.
  const isPending = user && !user.role && !user.is_staff && !user.is_superuser;
  if (isPending) return <PendingApprovalPage />;

  return (
    <div className="flex min-h-screen bg-canvas font-sans">
      {sidebarOpen && (
        // A pointer target only: the drawer's own Close menu button and Escape
        // are the keyboard route, so this is kept out of the tab order and the
        // tree rather than announced as a second "Close menu".
        <div
          aria-hidden
          className="fixed inset-0 bg-stone-900/40 z-40 md:hidden"
          onClick={dismiss}
        />
      )}

      <Sidebar
        ref={sidebarRef}
        inert={isPhone && !sidebarOpen}
        onDismiss={dismiss}
        className={cn(
          "md:translate-x-0",
          sidebarOpen ? "translate-x-0" : "-translate-x-full md:translate-x-0"
        )}
      />

      <div
        {...(drawerOpen ? { inert: "" } : {})}
        className={cn(
          "flex flex-col flex-1 min-w-0 transition-shell duration-200 ease-out motion-reduce:transition-none",
          // The sidebar's own widths: w-60, or the w-16 rail.
          collapsed ? "md:ml-16" : "md:ml-60",
        )}
      >
        {showPhoneBar && <PhoneBar ref={menuButtonRef} />}
        {/* The window is the scroll root, not `main` (IR-351). Nothing bounds
            main's height, so an `overflow-y-auto` here never scrolled; it only
            made main the nearest scroll container, which left every `sticky`
            descendant inert. No overflow value at all, not `overflow-x-clip`:
            a wide table with no scroll wrapper of its own must stay reachable
            by scrolling the window sideways, not be cut off. */}
        <main className={cn("flex-1", isFullBleed ? "p-0" : "p-4 sm:p-7")}>
          {isFullBleed ? (
            <Outlet />
          ) : (
            <PageContainer width={width}>
              <Breadcrumbs />
              <Outlet />
            </PageContainer>
          )}
        </main>
      </div>
    </div>
  );
}
