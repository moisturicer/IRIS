import { useRole } from "@/hooks/useRole";
import DashboardPage from "@/features/dashboard/DashboardPage";
import DiscoverPage from "@/features/discover/DiscoverPage";
import { PublishDialog } from "@/features/publish/PublishDialog";

/**
 * Role-aware home route: students see Discover, others see the stats dashboard.
 *
 * The Publish dialog lives here because `/?publish=...` is how it opens
 * (IR-408), for a Student or an Adviser alike. F1 removes the role split, and
 * Discover becomes home for everyone; the dialog stays on this route.
 */
export default function HomePage() {
  const { isStudent } = useRole();
  return (
    <>
      {isStudent ? <DiscoverPage /> : <DashboardPage />}
      <PublishDialog />
    </>
  );
}
