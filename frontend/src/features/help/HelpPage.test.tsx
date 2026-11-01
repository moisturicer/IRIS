/**
 * Help (IR-745): a reader sees help only for screens they can open, plus the
 * review overview and "Still stuck?", which everyone sees.
 *
 * Queries go through the accessible tree, by role and accessible name.
 */
import { afterEach, describe, expect, it } from "vitest";

import { ROLES } from "@/lib/constants";
import { useAuthStore } from "@/store/auth.store";
import { makeUser } from "@/test/authFixtures";
import { expectNoBlockingA11yViolations } from "@/test/axe";
import { renderScreen, screen, within } from "@/test/render";
import type { User } from "@/types/auth";

import HelpPage from "./HelpPage";

function renderAs(overrides: Partial<User>) {
  useAuthStore.setState({ user: makeUser(overrides), isAuthenticated: true });
  return renderScreen(<HelpPage />, { route: "/help" });
}

const section = (name: string) => screen.queryByRole("region", { name });

afterEach(() => useAuthStore.setState({ user: null, isAuthenticated: false }));

describe("Help", () => {
  it("lists its sections as contents that link to each one", async () => {
    const { container } = renderAs({ role_name: ROLES.STUDENT });

    expect(screen.getByRole("heading", { level: 1, name: "Help" })).toBeInTheDocument();
    const contents = screen.getByRole("navigation", { name: "Help contents" });
    expect(within(contents).getByRole("link", { name: "Asking IRIS" })).toHaveAttribute("href", "#ask-iris");
    expect(section("Asking IRIS")).toHaveAttribute("id", "ask-iris");
    await expectNoBlockingA11yViolations(container);
  });

  it("shows a Student how to publish, and nothing about reviewing or administration", () => {
    renderAs({ role_name: ROLES.STUDENT });

    expect(section("Publishing your research")).toBeInTheDocument();
    expect(section("Reviewing records")).not.toBeInTheDocument();
    expect(section("Coordinating your office")).not.toBeInTheDocument();
    expect(section("Workflow analytics")).not.toBeInTheDocument();
    expect(section("Administration")).not.toBeInTheDocument();
  });

  it("always explains the review workflow and who to contact", () => {
    renderAs({ role_name: ROLES.STUDENT });

    expect(section("How a record moves through review")).toBeInTheDocument();
    const stuck = section("Still stuck?")!;
    expect(within(stuck).getByText(/Research and Development Coordinating Office/)).toBeInTheDocument();
    // The product holds no contact route for RDCO, so Help invents none.
    expect(within(stuck).queryByRole("link")).not.toBeInTheDocument();
  });

  it("shows reviewing only to someone the server says has review work", () => {
    renderAs({ role_name: ROLES.ADVISER, review_access: { my_reviews: false, offices: [], is_coordinator: false } });
    expect(section("Reviewing records")).not.toBeInTheDocument();
  });

  it("shows an office member reviewing and analytics, but not coordination or publishing", () => {
    renderAs({ role_name: ROLES.ITSO, review_access: { my_reviews: true, offices: ["itso"], is_coordinator: false } });

    expect(section("Reviewing records")).toBeInTheDocument();
    expect(section("Workflow analytics")).toBeInTheDocument();
    expect(section("Coordinating your office")).not.toBeInTheDocument();
    expect(section("Publishing your research")).not.toBeInTheDocument();
  });

  it("shows a coordinator how to coordinate, and RDCO its administration", () => {
    renderAs({ role_name: ROLES.RDCO, review_access: { my_reviews: true, offices: ["rdco"], is_coordinator: true } });

    expect(section("Coordinating your office")).toBeInTheDocument();
    expect(section("Administration")).toBeInTheDocument();
  });
});
