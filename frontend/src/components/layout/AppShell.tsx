import { Outlet, useLocation } from "react-router-dom";
import { Sidebar } from "./Sidebar";
import { Header } from "./Header";
import { Breadcrumbs } from "./Breadcrumbs";
import { useUIStore } from "@/store/ui.store";
import { useAuth } from "@/hooks/useAuth";
import { PendingApprovalPage } from "@/features/auth/PendingApprovalPage";
import { cn } from "@/lib/utils";

export function AppShell() {
  const sidebarOpen  = useUIStore((s) => s.sidebarOpen);
  const closeSidebar = useUIStore((s) => s.closeSidebar);
  const { pathname } = useLocation();
  const isDiscoverHome = pathname === "/";

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
          className="fixed inset-0 bg-black/40 z-40 lg:hidden"
          aria-label="Close menu"
          onClick={closeSidebar}
        />
      )}

      <Sidebar
        className={cn(
          "transition-transform duration-200 ease-out",
          "lg:translate-x-0",
          sidebarOpen ? "translate-x-0" : "-translate-x-full lg:translate-x-0"
        )}
      />

      <div className="flex flex-col flex-1 min-w-0 lg:ml-[230px]">
        {!isDiscoverHome && <Header />}
        <main
          className={cn(
            "flex-1 overflow-y-auto",
            isDiscoverHome ? "pt-0 p-0" : "pt-[58px] p-4 sm:p-7"
          )}
        >
          {!isDiscoverHome && <Breadcrumbs />}
          <Outlet />
        </main>
      </div>
    </div>
  );
}
