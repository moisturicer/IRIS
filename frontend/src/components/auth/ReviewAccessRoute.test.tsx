/**
 * `ReviewAccessRoute` narrows `/review` by the server's `review_access` flag
 * (IR-916; the guard is IR-413, IR-415). It is read through what a visitor
 * sees: the queue, or Discover.
 */
import { beforeEach, describe, expect, it } from "vitest";
import { Route, Routes } from "react-router-dom";
import { act } from "@testing-library/react";

import { ReviewAccessRoute } from "./ReviewAccessRoute";
import { useAuthStore } from "@/store/auth.store";
import { ROLES } from "@/lib/constants";
import { pathFor } from "@/lib/access";
import { makeUser } from "@/test/authFixtures";
import type { User } from "@/types/auth";
import { renderScreen, screen } from "@/test/render";

function renderAt(route: string) {
  return renderScreen(
    <Routes>
      <Route element={<ReviewAccessRoute />}>
        <Route path="/review" element={<h1>Review queue</h1>} />
      </Route>
      <Route path={pathFor("discover")} element={<h1>Discover</h1>} />
    </Routes>,
    { route },
  );
}

function signInWith(reviewAccess: unknown) {
  useAuthStore.setState({
    user: makeUser({ role_name: ROLES.ADVISER, review_access: reviewAccess as User["review_access"] }),
    isAuthenticated: true,
  });
}

beforeEach(() => {
  useAuthStore.setState({ user: null, isAuthenticated: false });
});

describe("ReviewAccessRoute", () => {
  it("shows the queue to someone with review work", () => {
    signInWith({ my_reviews: true });

    renderAt("/review");

    expect(screen.getByRole("heading", { name: "Review queue" })).toBeInTheDocument();
  });

  it("sends an Adviser with no advisees to Discover, not an empty queue", () => {
    signInWith({ my_reviews: false });

    renderAt("/review");

    expect(screen.getByRole("heading", { name: "Discover" })).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Review queue" })).not.toBeInTheDocument();
  });

  it("sends a user the server sent no review_access for to Discover, never assuming access", () => {
    signInWith(undefined);

    renderAt("/review");

    expect(screen.getByRole("heading", { name: "Discover" })).toBeInTheDocument();
  });

  it("sends a signed-out visitor to Discover too; sign-in is ProtectedRoute's job, not this guard's", () => {
    renderAt("/review");

    expect(screen.getByRole("heading", { name: "Discover" })).toBeInTheDocument();
  });

  it.each([null, "true", 1])("only a strict true grants access, not %j", (value) => {
    signInWith({ my_reviews: value });

    renderAt("/review");

    expect(screen.getByRole("heading", { name: "Discover" })).toBeInTheDocument();
  });

  it("follows the flag when it changes under the page", () => {
    signInWith({ my_reviews: true });
    renderAt("/review");
    expect(screen.getByRole("heading", { name: "Review queue" })).toBeInTheDocument();

    act(() => signInWith({ my_reviews: false }));

    expect(screen.getByRole("heading", { name: "Discover" })).toBeInTheDocument();
  });
});
