import { SkeletonBlock } from "@/components/ui";
import { LoadingRegion } from "@/components/ui/LoadingRegion";

/**
 * Paper View's loading skeletons. Moved out of the page unchanged (IR-1267).
 */

/**
 * The main column while a record loads. On its own when the page already
 * shows a record and is moving to another, so Paper Chat beside it stays
 * mounted, conversation and all (IR-355).
 */
export function MainColumnSkeleton() {
  return (
    <div className="min-w-0 space-y-4" aria-hidden>
      <SkeletonBlock tone="strong" className="h-5 w-56" />
      <SkeletonBlock tone="strong" className="h-9 w-full" />
      <SkeletonBlock tone="strong" className="h-9 w-2/3" />
      <SkeletonBlock shape="card" className="h-32 w-full" />
    </div>
  );
}

export function LoadingSkeleton() {
  // The page announces its load once, as the other surfaces do (IR-939).
  return (
    <LoadingRegion label="Loading this record…" className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_20rem] items-start">
      <MainColumnSkeleton />
      <div className="space-y-4">
        <SkeletonBlock shape="card" className="h-44" />
        <SkeletonBlock shape="card" className="h-36" />
      </div>
    </LoadingRegion>
  );
}
