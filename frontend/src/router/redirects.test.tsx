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

// IR-1245: Help became a Settings section. An old link to one of its sections
// keeps the section, so it still lands on what it pointed at.
describe("an old link into Help", () => {
  function LandingWithHash() {
    const { pathname, search, hash } = useLocation();
    return <p>Landed on {`${pathname}${search}${hash}`}</p>;
  }
  function AppWithHash() {
    return useRoutes([...redirectRoutes, { path: "*", element: <LandingWithHash /> }]);
  }

  it("keeps the section it named", async () => {
    renderScreen(<AppWithHash />, { route: "/help#ask-iris" });

    expect(await screen.findByText("Landed on /settings?tab=help#ask-iris")).toBeInTheDocument();
  });
});

// IR-1304: editing your profile moved from its own page into Settings, so a
// bookmark or an old Help link to /profile/edit lands on Settings' Profile tab.
describe("an old link to Edit profile", () => {
  it("lands on Settings' Profile tab", async () => {
    renderScreen(<App />, { route: "/profile/edit" });

    expect(await screen.findByText("Landed on /settings?tab=profile")).toBeInTheDocument();
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
