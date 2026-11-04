/**
 * Old URLs that now lead somewhere else (spec §4.1).
 *
 * Bookmarks, notification links and emails already sent point at these paths,
 * so a removed screen redirects rather than 404s. One entry per URL, and
 * `redirects.test.tsx` follows every entry. The table is complete for §4.1's
 * six (IR-534). IR-783 removes old RDCO addresses without redirects (ADR-051).
 *
 * A `:param` in `path` carries into the same `:param` in `to`, so an old link
 * to a record's documents lands on that record.
 */
import { Navigate, useParams, type RouteObject } from "react-router-dom";

export const REDIRECTS: ReadonlyArray<{ path: string; to: string; why: string }> = [
  { path: "workspace", to: "/records/mine?section=research", why: "My Workspace became My Library's My research section (IR-410)" },
  { path: "records/add", to: "/?publish=new", why: "Submit Disclosure became the Publish dialog (IR-408)" },
  {
    path: "records/:id/documents",
    to: "/records/:id?section=files",
    why: "The documents page became Paper View's Files section (IR-411)",
  },
  {
    path: "records/:id/edit",
    to: "/records/:id?edit=details",
    why: "The edit page became Paper View's Edit details dialog (IR-411)",
  },
  {
    path: "review/:id/evaluate",
    to: "/records/:id?section=review",
    why: "The evaluation page became Paper View's Review section (IR-411)",
  },
  {
    path: "review/approved-proposals",
    to: "/review",
    why: "ADR-032 retired the Proposal complete act, and with it the Approved Proposals page (IR-534)",
  },
];

function RetiredUrl({ to }: { to: string }) {
  const params = useParams();
  const target = to.replace(/:(\w+)/g, (_, name: string) => encodeURIComponent(params[name] ?? ""));
  return <Navigate to={target} replace />;
}

export const redirectRoutes: RouteObject[] = REDIRECTS.map(({ path, to }) => ({
  path,
  element: <RetiredUrl to={to} />,
}));
