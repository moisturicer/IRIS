import { Outlet } from "react-router-dom";
import { DiscoverSearchProvider } from "@/contexts/DiscoverSearchContext";
import { Sidebar } from "./Sidebar";
import { Header } from "./Header";

export function AppShell() {
  return (
    <DiscoverSearchProvider>
      <div className="flex h-screen bg-gray-100 font-sans">
        <Sidebar />
        <div className="flex flex-col flex-1 ml-[230px]">
          <Header />
          <main className="flex-1 overflow-y-auto pt-[58px] p-7">
            <Outlet />
          </main>
        </div>
      </div>
    </DiscoverSearchProvider>
  );
}
