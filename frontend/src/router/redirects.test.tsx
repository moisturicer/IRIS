/**
 * Every retired URL lands where the table says (spec §4.1).
 *
 * A path with a parameter is followed with a sample value, which must reach
 * the destination unchanged: `/records/7/documents` lands on record 7.
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

/** Each `:param` filled with a sample value. */
const sample = (pattern: string) => pattern.replace(/:\w+/g, "7");

describe("retired URLs", () => {
  it.each(REDIRECTS)("/$path redirects to $to", async ({ path, to }) => {
    renderScreen(<App />, { route: `/${sample(path)}` });

    expect(await screen.findByText(`Landed on ${sample(to)}`)).toBeInTheDocument();
  });
});
