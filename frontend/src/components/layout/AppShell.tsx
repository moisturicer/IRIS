import { Outlet, useLocation, useMatches } from "react-router-dom";
import { Sidebar } from "./Sidebar";
import { Breadcrumbs, type RouteHandle } from "./Breadcrumbs";
import { NotificationBell } from "./NotificationBell";
import { PageContainer } from "./PageContainer";
import { useUIStore } from "@/store/ui.store";
import { useAuth } from "@/hooks/useAuth";
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
function PhoneBar() {
  const toggleSidebar = useUIStore((s) => s.toggleSidebar);
  return (
    <nav
      aria-label="Menu"
      className="md:hidden flex items-center justify-between gap-3 h-14 px-4 bg-white border-b border-stone-200"
    >
      <button
        type="button"
        onClick={toggleSidebar}
        className="w-10 h-10 rounded-lg border border-stone-200 flex items-center justify-center text-stone-600 hover:bg-stone-50"
        aria-label="Open menu"
      >
        <i className="fas fa-bars text-base" aria-hidden />
      </button>
      <NotificationBell />
    </nav>
  );
}

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

  const { user } = useAuth();
  // Block users who are logged in but whose role request hasn't been approved yet.
  // Django staff/superuser accounts (no role) are exempt.
  const isPending = user && !user.role && !user.is_staff && !user.is_superuser;
  if (isPending) return <PendingApprovalPage />;

  return (
    <div className="flex min-h-screen bg-gray-100 font-sans">
      {sidebarOpen && (
        <button
          type="button"
          className="fixed inset-0 bg-black/40 z-40 md:hidden"
          aria-label="Close menu"
          onClick={closeSidebar}
        />
      )}

      <Sidebar
        className={cn(
          "transition-transform duration-200 ease-out",
          "md:translate-x-0",
          sidebarOpen ? "translate-x-0" : "-translate-x-full md:translate-x-0"
        )}
      />

      <div
        className={cn(
          "flex flex-col flex-1 min-w-0 transition-[margin] duration-200 ease-out",
          collapsed ? "md:ml-[60px]" : "md:ml-[230px]",
        )}
      >
        {showPhoneBar && <PhoneBar />}
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
