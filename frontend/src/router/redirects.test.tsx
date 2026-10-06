/**
 * Every retired URL lands where the table says (spec §4.1).
 */
import { describe, expect, it } from "vitest";
import { useLocation, useRoutes } from "react-router-dom";

import { renderScreen, screen } from "@/test/render";

import { REDIRECTS, redirectRoutes } from "./redirects";

function Landing() {
  const location = useLocation();
  return <p>Landed on {`${location.pathname}${location.search}`}</p>;
}

function App() {
  return useRoutes([...redirectRoutes, { path: "*", element: <Landing /> }]);
}

describe("retired URLs", () => {
  it.each(REDIRECTS)("/$path redirects to $to", async ({ path, to }) => {
    renderScreen(<App />, { route: `/${path}` });

    expect(await screen.findByText(`Landed on ${to}`)).toBeInTheDocument();
  });
});
