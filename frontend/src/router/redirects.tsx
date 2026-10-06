/**
 * Old URLs that now lead somewhere else (spec §4.1).
 *
 * Bookmarks, notification links and emails already sent point at these paths,
 * so a removed screen redirects rather than 404s. One entry per URL, and
 * `redirects.test.tsx` follows every entry. F1 adds the rest of the table.
 */
import { Navigate, type RouteObject } from "react-router-dom";

export const REDIRECTS: ReadonlyArray<{ path: string; to: string; why: string }> = [
  { path: "records/add", to: "/?publish=new", why: "Submit Disclosure became the Publish dialog (IR-408)" },
];

export const redirectRoutes: RouteObject[] = REDIRECTS.map(({ path, to }) => ({
  path,
  element: <Navigate to={to} replace />,
}));
