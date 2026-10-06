/**
 * Old URLs that now lead somewhere else (spec §4.1).
 *
 * Bookmarks, notification links and emails already sent point at these paths,
 * so a removed screen redirects rather than 404s. One entry per URL, and
 * `redirects.test.tsx` follows every entry. F1 adds the rest of the table.
 *
 * A `:param` in `path` carries into the same `:param` in `to`, so an old link
 * to a record's documents lands on that record.
 */
import { Navigate, useParams, type RouteObject } from "react-router-dom";

export const REDIRECTS: ReadonlyArray<{ path: string; to: string; why: string }> = [
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
