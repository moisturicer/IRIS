/**
 * The breadcrumb trail's first step is Discover, the page it leads to (IR-1085,
 * audit NAV-03). It used to say "Home" for a page the sidebar calls Discover.
 */
import { describe, expect, it } from "vitest";
import { render, screen, within } from "@testing-library/react";
import { createMemoryRouter, Outlet, RouterProvider } from "react-router-dom";

import { Breadcrumbs } from "./Breadcrumbs";

function renderAt(path: string) {
  const router = createMemoryRouter(
    [
      {
        element: (
          <>
            <Breadcrumbs />
            <Outlet />
          </>
        ),
        children: [
          { path: "/", element: <h1>Discover page</h1>, handle: { crumb: "Discover" } },
          { path: "/review", element: <h1>My Reviews page</h1>, handle: { crumb: "My Reviews" } },
          {
            path: "/profile", handle: { crumb: "Profile" },
            children: [{ path: "edit", element: <h1>Edit</h1>, handle: { crumb: "Edit profile" } }],
          },
        ],
      },
    ],
    { initialEntries: [path] },
  );
  return render(<RouterProvider router={router} />);
}

const trail = () => screen.getByRole("navigation", { name: "Breadcrumb" });

describe("Breadcrumbs", () => {
  it("starts with a link named Discover, never Home", () => {
    renderAt("/review");

    expect(within(trail()).getByRole("link", { name: "Discover" })).toHaveAttribute("href", "/");
    expect(within(trail()).queryByText("Home")).not.toBeInTheDocument();
    expect(within(trail()).getByText("My Reviews")).toHaveAttribute("aria-current", "page");
  });

  it("names Discover once, as the current page, when you are on it", () => {
    renderAt("/");

    expect(within(trail()).getAllByText("Discover")).toHaveLength(1);
    expect(within(trail()).getByText("Discover")).toHaveAttribute("aria-current", "page");
    expect(within(trail()).queryByRole("link")).not.toBeInTheDocument();
  });

  it("keeps a nested page's parents between Discover and the page", () => {
    renderAt("/profile/edit");

    expect(within(trail()).getAllByRole("listitem").map((li) => li.textContent?.replace("/", "").trim()))
      .toEqual(["Discover", "Profile", "Edit profile"]);
  });
});
