import { Link, useLocation, useNavigate } from "react-router-dom";

import { StatusScreen } from "@/components/shared/StatusScreen";
import { PILL_PRIMARY, PILL_SECONDARY } from "@/components/ui/pillStyles";
import { FOCUS_RING } from "@/components/ui/interaction";
import { pathFor } from "@/lib/access";
import { cn } from "@/lib/utils";

interface NotFoundScreenProps {
  /**
   * What was asked for, when the page knows (`"Record"`). Without one the
   * screen speaks of a page: the address itself matched nothing.
   */
  subject?: string;
}

/**
 * Nothing to show at this address (IR-745).
 *
 * One wording for "does not exist" and "exists but is not yours to see",
 * because the API answers both with the same 404 and never says which
 * (IR-153). Saying "you don't have access" would confirm that someone else's
 * draft exists, so this screen never does.
 */
export function NotFoundScreen({ subject }: NotFoundScreenProps) {
  const navigate = useNavigate();
  // The first entry of a session has the key "default": there is no page in
  // IRIS to go back to, and Back would leave the site instead.
  const canGoBack = useLocation().key !== "default";
  const thing = subject ? subject.toLowerCase() : "page";

  return (
    <StatusScreen
      icon={subject ? "fa-file-circle-question" : "fa-compass"}
      title={subject ? `${subject} not available` : "Page not found"}
      message={`This ${thing} doesn't exist, or it isn't available to you.`}
      code="Error 404"
      actions={
        <>
          <Link to={pathFor("discover")} className={cn(PILL_PRIMARY, FOCUS_RING)}>
            Go to Discover
          </Link>
          {canGoBack && (
            <button type="button" onClick={() => navigate(-1)} className={cn(PILL_SECONDARY, FOCUS_RING)}>
              Go back
            </button>
          )}
        </>
      }
    />
  );
}
