/**
 * Another person's Profile (IR-700), as a prototype over sample people: what a
 * reader sees, what is left out, how a long list pages, and where a hidden or
 * your-own profile goes. Asserted through the accessible tree. The samples are
 * `publicProfile.ts`; when IR-696 ships these tests move to the API's shapes.
 */
import { Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it } from "vitest";

import { useAuthStore } from "@/store/auth.store";
import { expectNoBlockingA11yViolations } from "@/test/axe";
import { renderScreen, screen, userEvent, within } from "@/test/render";

import PersonProfilePage from "./PersonProfilePage";

function open(id: number | string) {
  return renderScreen(
    <Routes>
      <Route path="/people/:id" element={<PersonProfilePage />} />
      <Route path="/profile" element={<p>Your own profile</p>} />
    </Routes>,
    { route: `/people/${id}` },
  );
}

beforeEach(() => {
  useAuthStore.setState({
    user: { id: 7, first_name: "Ana", last_name: "Reyes", role_name: "Student" } as never,
    isAuthenticated: true,
    authReady: true,
  });
});

describe("a full profile", () => {
  it("names the person, their role, affiliation and the university", () => {
    open(101);

    expect(screen.getByRole("heading", { level: 1, name: "Marites C. Villanueva" })).toBeVisible();
    expect(screen.getByText("Adviser")).toBeVisible();
    expect(screen.getByText("College of Engineering and Architecture · Department of Computer Engineering")).toBeVisible();
    expect(screen.getByText("Cebu Institute of Technology – University")).toBeVisible();
    expect(screen.getByRole("img", { name: "Marites C. Villanueva" })).toBeVisible();
  });

  it("shows About, interests, Research, Advised and Collaborators, with no totals in a heading", () => {
    open(101);

    for (const name of ["About", "Research interests", "Research", "Advised", "Collaborators"]) {
      expect(screen.getByRole("heading", { level: 2, name })).toBeVisible();
    }
    expect(screen.getByRole("list", { name: "Research interests" })).toHaveTextContent("Flood risk");
  });

  it("gives each paper its own views, linked to the paper", () => {
    open(101);
    const research = screen.getByRole("list", { name: "Research" });

    const first = within(research).getAllByRole("listitem")[0];
    expect(within(first).getByRole("link", { name: /Flood Susceptibility Mapping/ }))
      .toHaveAttribute("href", "/records/500");
    expect(first).toHaveTextContent("48 views");
  });

  it("never prints an email address or a citation count", () => {
    const { container } = open(101);

    expect(container.textContent).not.toMatch(/@/);
    expect(container.textContent).not.toMatch(/citation|h-index|follower/i);
  });

  it("links each collaborator to their profile, with the papers they shared", () => {
    open(101);
    const rail = screen.getByRole("complementary", { name: "Collaborators" });

    expect(within(rail).getByRole("link", { name: "Ana L. Reyes" })).toHaveAttribute("href", "/people/201");
    expect(rail).toHaveTextContent("14 shared papers");
  });

  it("has no blocking accessibility violations", async () => {
    const { container } = open(101);
    await expectNoBlockingA11yViolations(container);
  });
});

describe("long lists", () => {
  it("loads ten advised papers at a time and puts focus on the first new one", async () => {
    open(101);
    const advised = screen.getByRole("list", { name: "Advised" });
    expect(within(advised).getAllByRole("listitem")).toHaveLength(10);

    await userEvent.click(screen.getByRole("button", { name: "Show more advised papers" }));

    const rows = within(advised).getAllByRole("listitem");
    expect(rows).toHaveLength(14);
    expect(within(rows[10]).getByRole("link")).toHaveFocus();
    // Everything is shown, so there is nothing more to ask for.
    expect(screen.queryByRole("button", { name: "Show more advised papers" })).not.toBeInTheDocument();
  });

  it("loads twelve collaborators at a time", async () => {
    open(101);
    const rail = screen.getByRole("complementary", { name: "Collaborators" });
    expect(within(rail).getAllByRole("listitem")).toHaveLength(12);

    await userEvent.click(within(rail).getByRole("button", { name: "Show more collaborators" }));

    expect(within(rail).getAllByRole("listitem")).toHaveLength(15);
  });

  it("does not offer Show more when everything fits", () => {
    open(102);

    expect(screen.queryByRole("button", { name: /Show more/ })).not.toBeInTheDocument();
  });
});

describe("a short or empty profile", () => {
  it("leaves out sections with nothing in them", () => {
    open(102);

    expect(screen.getByRole("heading", { level: 2, name: "Research" })).toBeVisible();
    expect(screen.queryByRole("heading", { name: "Advised" })).not.toBeInTheDocument();
  });

  it("says so once when there is nothing published, and shows no empty sections", () => {
    open(103);

    expect(screen.getByText("No published papers yet.")).toBeVisible();
    for (const name of ["About", "Research interests", "Research", "Advised", "Collaborators"]) {
      expect(screen.queryByRole("heading", { name })).not.toBeInTheDocument();
    }
    // No photo: the initials stand in, and they are not announced as an image.
    expect(screen.queryByRole("img")).not.toBeInTheDocument();
  });

  it("names an office as the role, and leaves out an affiliation nobody recorded", () => {
    open(105);

    expect(screen.getByText("RDCO")).toBeVisible();
    expect(screen.queryByText(/College of/)).not.toBeInTheDocument();
  });

  it("opens a person the rail named, from their own short page", () => {
    open(203);

    expect(screen.getByRole("heading", { level: 1, name: "Grace T. Lim" })).toBeVisible();
  });
});

describe("what the reader may not see", () => {
  it("shows the standard not-found screen for a suspended profile", () => {
    open(104);

    expect(screen.getByRole("heading", { name: "Profile not available" })).toBeVisible();
    expect(screen.getByText("This profile doesn't exist, or it isn't available to you.")).toBeVisible();
  });

  it("answers a person who does not exist the same way", () => {
    open(99999);

    expect(screen.getByRole("heading", { name: "Profile not available" })).toBeVisible();
  });

  it("sends your own id to your own profile", () => {
    open(7);

    expect(screen.getByText("Your own profile")).toBeVisible();
  });
});
