import { Navigate, Outlet } from "react-router-dom";
import { useAuthStore } from "@/store/auth.store";
import { hasReviewWork, pathFor } from "@/lib/access";

/**
 * My Reviews, for a user who has review work (IR-413, spec §4.2).
 *
 * Sits inside `ProtectedRoute`, which keeps the role as the outer gate. This
 * narrows it by the server's `review_access.my_reviews` (IR-415): an Adviser
 * with no advisees has the role but nothing to review, so `/review` sends them
 * to Discover instead of an empty queue -- the same flag that keeps My Reviews
 * out of their sidebar, read through the same `hasReviewWork`.
 *
 * A redirect, not the forbidden screen: the page is not refused, there is
 * just nothing on it for this user yet. UX only; the queue endpoint scopes
 * every row on the server.
 */
export function ReviewAccessRoute() {
  const reviewAccess = useAuthStore((s) => s.user?.review_access);
  if (!hasReviewWork(reviewAccess)) return <Navigate to={pathFor("discover")} replace />;
  return <Outlet />;
}
