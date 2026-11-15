import { Navigate, useParams } from "react-router-dom";

import { EmptyState } from "@/components/shared/EmptyState";
import { InterruptedState } from "@/components/shared/InterruptedState";
import { FOCUS_RING } from "@/components/ui/interaction";
import { LoadingRegion } from "@/components/ui/LoadingRegion";
import { SkeletonBlock } from "@/components/ui/Skeleton";
import { PILL_SECONDARY } from "@/components/ui/pillStyles";
import { NotFoundScreen } from "@/features/errors/NotFoundScreen";
import { useAuth } from "@/hooks/useAuth";
import { pathFor } from "@/lib/access";
import { cn } from "@/lib/utils";

import { PersonProfileView } from "./PersonProfileView";
import { usePersonProfile } from "./usePersonProfile";

/**
 * `/people/:id`: another person's Profile (IR-700), read from the draft IR-696
 * contract (`api/people.ts`).
 *
 * Two rules are the real ones: your own id goes to your own Profile, where Edit
 * profile lives; and a person the server hides (suspended, a System Admin,
 * missing) gets the same not-found screen as an address that matches nothing,
 * so the page never confirms that a hidden account exists. Until IR-696 ships
 * every id answers 404 and so lands there.
 */
export default function PersonProfilePage() {
  const { user } = useAuth();
  const id = Number(useParams().id);

  if (!Number.isInteger(id) || id < 1) return <NotFoundScreen subject="Profile" />;
  if (user && user.id === id) return <Navigate to={pathFor("profile")} replace />;
  return <PersonProfile key={id} id={id} />;
}

function PersonProfile({ id }: { id: number }) {
  const { state, retry, more } = usePersonProfile(id);

  switch (state.kind) {
    case "loading":
      return <ProfileSkeleton />;
    case "not_found":
      return <NotFoundScreen subject="Profile" />;
    case "failed":
      return state.interrupted ? (
        <InterruptedState framed what="profile" onRetry={retry} />
      ) : (
        <EmptyState
          framed
          tone="error"
          icon="fa-triangle-exclamation"
          title="We couldn't load this profile"
          message={state.message}
          action={<button type="button" onClick={retry} className={cn(PILL_SECONDARY, FOCUS_RING)}>Try again</button>}
        />
      );
    case "ready":
      return <PersonProfileView profile={state.model.profile} lists={{ ...state.model, onMore: more }} />;
  }
}

/** The header and two sections in the page's own shape, announced once as loading. */
function ProfileSkeleton() {
  return (
    <LoadingRegion label="Loading profile…" className="max-w-4xl">
      <div className="flex items-start gap-6">
        <SkeletonBlock shape="pill" className="h-20 w-20 shrink-0 sm:h-28 sm:w-28" />
        <div className="mt-2 flex-1 space-y-3">
          <SkeletonBlock className="h-6 w-1/2" />
          <SkeletonBlock className="h-4 w-1/4" />
          <SkeletonBlock className="h-4 w-2/3" />
        </div>
      </div>
      <div className="mt-8 space-y-3 border-t border-stone-200 pt-8">
        <SkeletonBlock className="h-3 w-full" />
        <SkeletonBlock className="h-3 w-11/12" />
        <SkeletonBlock className="h-3 w-2/3" />
      </div>
    </LoadingRegion>
  );
}
