import { useRole } from "@/hooks/useRole";
import DashboardPage from "@/features/dashboard/DashboardPage";
import DiscoverPage from "@/features/discover/DiscoverPage";

/** Role-aware home route: students see Discover, others see the stats dashboard. */
export default function HomePage() {
  const { isStudent } = useRole();
  return isStudent ? <DiscoverPage /> : <DashboardPage />;
}
