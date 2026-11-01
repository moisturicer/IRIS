import DiscoverPage from "@/features/discover/DiscoverPage";
import { PublishDialog } from "@/features/publish/PublishDialog";

/**
 * The home route: Discover, for every role (IR-534, spec §4.1).
 *
 * There was a role split here -- students saw Discover, everyone else a
 * stats dashboard -- which F1 removes. Where a user lands after signing in is
 * a separate decision, `lib/landing.ts`: a reviewer with work goes to My
 * Reviews, but `/` is Discover for them too.
 *
 * The Publish dialog lives here because `/?publish=...` is how it opens
 * (IR-408), for a Student or an Adviser alike.
 */
export default function HomePage() {
  return (
    <>
      <DiscoverPage />
      <PublishDialog />
    </>
  );
}
