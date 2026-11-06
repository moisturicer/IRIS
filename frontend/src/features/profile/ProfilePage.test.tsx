/**
 * Your own Profile page (IR-933): what other signed-in people see of you, with
 * the way to edit it. Asserted through the accessible tree. The page reads the
 * signed-in user; another person's profile is IR-700.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { profileApi } from "@/api/profile";
import { useAuthStore } from "@/store/auth.store";
import { expectNoBlockingA11yViolations } from "@/test/axe";
import { renderScreen, screen } from "@/test/render";

import ProfilePage from "./ProfilePage";

const baseUser = {
  id: 7, email: "ana@cit.edu", first_name: "Ana", middle_initial: "L", last_name: "Reyes",
  role_name: "Student", college_name: "College of Computer Studies", department_name: "",
  course_name: "BS Computer Science",
  bio: "", research_interests: [] as string[], orcid: null as string | null, photo_url: null as string | null,
};

function signIn(overrides: Partial<typeof baseUser> = {}) {
  useAuthStore.setState({
    user: { ...baseUser, ...overrides } as never,
    isAuthenticated: true,
    authReady: true,
  });
}

beforeEach(() => {
  signIn();
  vi.stubGlobal("URL", Object.assign(URL, {
    createObjectURL: vi.fn().mockReturnValue("blob:photo"),
    revokeObjectURL: vi.fn(),
  }));
});

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

describe("the profile", () => {
  it("names the person, their role and where they are", () => {
    renderScreen(<ProfilePage />, { route: "/profile" });

    expect(screen.getByRole("heading", { level: 1, name: "Ana L. Reyes" })).toBeVisible();
    expect(screen.getByText("Student")).toBeVisible();
    expect(screen.getByText("College of Computer Studies · BS Computer Science")).toBeVisible();
  });

  it("shows the bio, the interests and the ORCID iD as a link", () => {
    signIn({
      bio: "Coastal flood mapping.",
      research_interests: ["GIS", "Remote sensing"],
      orcid: "0000-0002-1825-0097",
    });
    renderScreen(<ProfilePage />, { route: "/profile" });

    expect(screen.getByText("Coastal flood mapping.")).toBeVisible();
    const interests = screen.getByRole("list", { name: "Research interests" });
    expect(interests).toHaveTextContent("GIS");
    expect(interests).toHaveTextContent("Remote sensing");
    expect(screen.getByRole("link", { name: "0000-0002-1825-0097" }))
      .toHaveAttribute("href", "https://orcid.org/0000-0002-1825-0097");
  });

  it("leaves out what was left empty, with no placeholder", () => {
    renderScreen(<ProfilePage />, { route: "/profile" });

    expect(screen.queryByRole("heading", { name: "About" })).not.toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Research interests" })).not.toBeInTheDocument();
    expect(screen.queryByText(/ORCID/)).not.toBeInTheDocument();
  });

  it("never prints the account's email address", () => {
    renderScreen(<ProfilePage />, { route: "/profile" });

    expect(screen.queryByText("ana@cit.edu")).not.toBeInTheDocument();
  });

  it("falls back to initials, and fetches the photo with auth when there is one", async () => {
    const { rerender } = renderScreen(<ProfilePage />, { route: "/profile" });
    expect(screen.queryByRole("img")).not.toBeInTheDocument();

    signIn({ photo_url: "/users/7/photo/?v=1" });
    vi.spyOn(profileApi, "photo").mockResolvedValue({ data: new Blob(["png"]) } as never);
    rerender(<ProfilePage />);

    expect(await screen.findByRole("img", { name: "Ana L. Reyes" })).toBeVisible();
  });
});

describe("editing", () => {
  it("offers Edit profile, which opens the edit page", () => {
    renderScreen(<ProfilePage />, { route: "/profile" });

    expect(screen.getByRole("link", { name: "Edit profile" })).toHaveAttribute("href", "/profile/edit");
  });

  it("says this is how others see you", () => {
    renderScreen(<ProfilePage />, { route: "/profile" });

    expect(screen.getByRole("note")).toHaveTextContent(/how other people signed in to IRIS see you/i);
  });

  it("has no blocking accessibility violations", async () => {
    signIn({ bio: "Floods.", research_interests: ["GIS"], orcid: "0000-0002-1825-0097" });
    const { container } = renderScreen(<ProfilePage />, { route: "/profile" });

    await expectNoBlockingA11yViolations(container);
  });
});
