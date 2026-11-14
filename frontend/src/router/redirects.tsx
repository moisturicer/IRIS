/**
 * Old URLs that now lead somewhere else (spec §4.1).
 *
 * Bookmarks, notification links and emails already sent point at these paths,
 * so a removed screen redirects rather than 404s. One entry per URL, and
 * `redirects.test.tsx` follows every entry. The table is complete for §4.1's
 * six (IR-534). IR-783 removes old RDCO addresses without redirects (ADR-051).
 *
 * A `:param` in `path` carries into the same `:param` in `to`, so an old link
 * to a record's documents lands on that record. `byRole` sends a role whose
 * old page went somewhere else to its own destination instead of `to`.
 */
import { Navigate, useParams, type RouteObject } from "react-router-dom";
import { ROLES, type RoleName } from "@/lib/constants";
import { useAuthStore } from "@/store/auth.store";

export const REDIRECTS: ReadonlyArray<{
  path: string; to: string; byRole?: Partial<Record<RoleName, string>>; why: string;
}> = [
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
  {
    path: "notices",
    to: "/rdco/setup?section=notice",
    byRole: { [ROLES.SYSTEM_ADMIN]: "/admin/audit?event_type=NOTICE_PUBLISHED" },
    why: "The Notices page became Setup's Notice section; the System Admin reads publications in the Audit Log (ADR-063 decision 9, IR-972)",
  },
];

function RetiredUrl({ to, byRole }: { to: string; byRole?: Partial<Record<RoleName, string>> }) {
  const params = useParams();
  const role = useAuthStore((state) => state.user?.role_name) as RoleName | undefined;
  const target = ((role && byRole?.[role]) || to).replace(/:(\w+)/g, (_, name: string) => encodeURIComponent(params[name] ?? ""));
  return <Navigate to={target} replace />;
}

export const redirectRoutes: RouteObject[] = REDIRECTS.map(({ path, to, byRole }) => ({
  path,
  element: <RetiredUrl to={to} byRole={byRole} />,
}));
