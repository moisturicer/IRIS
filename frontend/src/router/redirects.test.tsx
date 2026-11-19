/**
 * Every retired URL lands where the table says (spec §4.1).
 *
 * A path with a parameter is followed with a sample value, which must reach
 * the destination unchanged: `/records/7/documents` lands on record 7.
 */
import { describe, expect, it } from "vitest";
import { useLocation, useRoutes } from "react-router-dom";

import { ROLES } from "@/lib/constants";
import { useAuthStore } from "@/store/auth.store";
import { makeUser } from "@/test/authFixtures";
import { renderScreen, screen } from "@/test/render";

import { REDIRECTS, redirectRoutes } from "./redirects";

function Landing() {
  const location = useLocation();
  return <p>Landed on {`${location.pathname}${location.search}`}</p>;
}

function App() {
  return useRoutes([...redirectRoutes, { path: "*", element: <Landing /> }]);
}

/** Each `:param` filled with a sample value. */
const sample = (pattern: string) => pattern.replace(/:\w+/g, "7");

describe("retired URLs", () => {
  it.each(REDIRECTS)("/$path redirects to $to", async ({ path, to }) => {
    renderScreen(<App />, { route: `/${sample(path)}` });

    expect(await screen.findByText(`Landed on ${sample(to)}`)).toBeInTheDocument();
  });
});

// ADR-063 decision 9 (IR-972): the Notices page became Setup's Notice section,
// which is RDCO's. The System Admin, who reads publications in the Audit Log,
// lands there instead, filtered to them.
describe("an old link to the Notices page", () => {
  it.each([
    [ROLES.RDCO, "/rdco/setup?section=notice"],
    [ROLES.SYSTEM_ADMIN, "/admin/audit?event_type=NOTICE_PUBLISHED"],
  ])("takes %s to %s", async (role, to) => {
    useAuthStore.setState({ user: makeUser({ role_name: role }), accessToken: "t", isAuthenticated: true, authReady: true });

    renderScreen(<App />, { route: "/notices" });

    expect(await screen.findByText(`Landed on ${to}`)).toBeInTheDocument();
  });
});
