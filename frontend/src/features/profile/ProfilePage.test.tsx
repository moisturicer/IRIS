/**
 * Your own Profile page (IR-933): what other signed-in people see of you, with
 * the way to edit it. Asserted through the accessible tree. The page reads the
 * signed-in user; another person's profile is IR-700.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { peopleApi } from "@/api/people";
import { profileApi } from "@/api/profile";
import type { Collaborator, ProfilePaper } from "@/types/people";
import { useAuthStore } from "@/store/auth.store";
import { expectNoBlockingA11yViolations } from "@/test/axe";
import { renderScreen, screen, userEvent, waitFor, within } from "@/test/render";

import ProfilePage from "./ProfilePage";

const paper = (id: number): ProfilePaper => ({
  id, title: `Paper ${id}`, authors: ["Reyes, A."], classification_name: "Geomatics",
  record_type_name: "Thesis / Research", publication_year: 2025, views: 48,
});
const collaborator = (id: number): Collaborator => ({
  id, first_name: "Marites", middle_initial: "C", last_name: "Villanueva", photo_url: null, shared_papers: 2,
});
const page = <T,>(results: T[], more = false) => ({ data: { results, next: more ? "next" : null } }) as never;

const baseUser = {
  id: 7, email: "ana@cit.edu", first_name: "Ana", middle_initial: "L", last_name: "Reyes",
  role_name: "Student", college_name: "College of Computer Studies", department_name: "",
  course_name: "BS Computer Science",
  bio: "", research_interests: [] as string[], photo_url: null as string | null,
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
  vi.spyOn(peopleApi, "research").mockResolvedValue(page([]));
  vi.spyOn(peopleApi, "advised").mockResolvedValue(page([]));
  vi.spyOn(peopleApi, "collaborators").mockResolvedValue(page([]));
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

  it("names the university under the affiliation, as another person's Profile does (IR-948)", () => {
    renderScreen(<ProfilePage />, { route: "/profile" });

    expect(screen.getByText("Cebu Institute of Technology – University")).toBeVisible();
  });

  it("loads Research, Advised and Collaborators for the signed-in account (IR-949)", async () => {
    vi.spyOn(peopleApi, "research").mockResolvedValue(page([paper(500)]) as never);
    vi.spyOn(peopleApi, "advised").mockResolvedValue(page([paper(600)]) as never);
    vi.spyOn(peopleApi, "collaborators").mockResolvedValue(page([collaborator(201)]) as never);
    renderScreen(<ProfilePage />, { route: "/profile" });

    expect(await screen.findByRole("link", { name: "Paper 500" })).toBeVisible();
    expect(screen.getByRole("link", { name: "Paper 600" })).toBeVisible();
    expect(screen.getByRole("complementary", { name: "Collaborators" })).toHaveTextContent("2 shared papers");
    expect(peopleApi.research).toHaveBeenCalledWith(7, 1);
    expect(peopleApi.advised).toHaveBeenCalledWith(7, 1);
    expect(peopleApi.collaborators).toHaveBeenCalledWith(7, 1);
  });

  it("says there are no published papers when both paper lists are empty", async () => {
    vi.spyOn(peopleApi, "research").mockResolvedValue(page([]) as never);
    vi.spyOn(peopleApi, "advised").mockResolvedValue(page([]) as never);
    vi.spyOn(peopleApi, "collaborators").mockResolvedValue(page([]) as never);
    renderScreen(<ProfilePage />, { route: "/profile" });

    expect(await screen.findByText("No published papers yet.")).toBeVisible();
    expect(screen.queryByRole("heading", { name: "Research" })).not.toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Advised" })).not.toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Collaborators" })).not.toBeInTheDocument();
  });

  it("does not call pending paper lists empty", async () => {
    let finishResearch!: (result: never) => void;
    let finishAdvised!: (result: never) => void;
    vi.spyOn(peopleApi, "research").mockReturnValue(new Promise((resolve) => { finishResearch = resolve; }) as never);
    vi.spyOn(peopleApi, "advised").mockReturnValue(new Promise((resolve) => { finishAdvised = resolve; }) as never);
    renderScreen(<ProfilePage />, { route: "/profile" });

    expect(screen.queryByText("No published papers yet.")).not.toBeInTheDocument();
    finishResearch(page([]));
    finishAdvised(page([]));
    expect(await screen.findByText("No published papers yet.")).toBeVisible();
  });

  it("keeps a failed list in place and retries only that list", async () => {
    const research = vi.spyOn(peopleApi, "research")
      .mockRejectedValueOnce({ response: { status: 500, data: {} } } as never)
      .mockResolvedValue(page([paper(500)]) as never);
    vi.spyOn(peopleApi, "advised").mockResolvedValue(page([paper(600)]) as never);
    vi.spyOn(peopleApi, "collaborators").mockResolvedValue(page([]) as never);
    renderScreen(<ProfilePage />, { route: "/profile" });

    const section = (await screen.findByRole("heading", { level: 2, name: "Research" })).closest("section")!;
    expect(within(section).getByRole("alert")).toBeVisible();
    expect(screen.getByRole("link", { name: "Paper 600" })).toBeVisible();

    await userEvent.click(within(section).getByRole("button", { name: "Try again" }));
    expect(await screen.findByRole("link", { name: "Paper 500" })).toBeVisible();
    expect(research).toHaveBeenLastCalledWith(7, 1);
  });

  it("pages its own Research list and focuses the first new paper", async () => {
    const first = Array.from({ length: 10 }, (_, i) => paper(700 + i));
    const second = [paper(710), paper(711)];
    const research = vi.spyOn(peopleApi, "research").mockImplementation((_id, n) =>
      Promise.resolve((n === 1 ? page(first, true) : page(second)) as never));
    vi.spyOn(peopleApi, "advised").mockResolvedValue(page([]) as never);
    vi.spyOn(peopleApi, "collaborators").mockResolvedValue(page([]) as never);
    renderScreen(<ProfilePage />, { route: "/profile" });
    const list = await screen.findByRole("list", { name: "Research" });

    await userEvent.click(screen.getByRole("button", { name: "Show more research papers" }));
    await waitFor(() => expect(within(list).getAllByRole("listitem")).toHaveLength(12));

    expect(research).toHaveBeenLastCalledWith(7, 2);
    expect(within(within(list).getAllByRole("listitem")[10]).getByRole("link")).toHaveFocus();
  });

  it("pages its own Collaborators list and focuses the first new person", async () => {
    const first = Array.from({ length: 12 }, (_, i) => collaborator(800 + i));
    const second = [collaborator(812)];
    const collaborators = vi.spyOn(peopleApi, "collaborators").mockImplementation((_id, n) =>
      Promise.resolve((n === 1 ? page(first, true) : page(second)) as never));
    renderScreen(<ProfilePage />, { route: "/profile" });
    const rail = await screen.findByRole("complementary", { name: "Collaborators" });

    await userEvent.click(within(rail).getByRole("button", { name: "Show more collaborators" }));
    await waitFor(() => expect(within(rail).getAllByRole("listitem")).toHaveLength(13));

    expect(collaborators).toHaveBeenLastCalledWith(7, 2);
    expect(within(within(rail).getAllByRole("listitem")[12]).getByRole("link")).toHaveFocus();
  });

  it("has no blocking accessibility violations with the profile lists present", async () => {
    vi.spyOn(peopleApi, "research").mockResolvedValue(page([paper(500)]) as never);
    vi.spyOn(peopleApi, "advised").mockResolvedValue(page([]) as never);
    vi.spyOn(peopleApi, "collaborators").mockResolvedValue(page([collaborator(201)]) as never);
    const { container } = renderScreen(<ProfilePage />, { route: "/profile" });

    await screen.findByRole("link", { name: "Paper 500" });
    await expectNoBlockingA11yViolations(container);
  });

  it("does not request profile lists while signed out", () => {
    useAuthStore.setState({ user: null, isAuthenticated: false, authReady: true });
    renderScreen(<ProfilePage />, { route: "/profile" });

    expect(peopleApi.research).not.toHaveBeenCalled();
    expect(peopleApi.advised).not.toHaveBeenCalled();
    expect(peopleApi.collaborators).not.toHaveBeenCalled();
  });

  it("shows no role line for a person who has no role yet", () => {
    signIn({ role_name: null as never });
    renderScreen(<ProfilePage />, { route: "/profile" });

    expect(screen.getByRole("heading", { level: 1, name: "Ana L. Reyes" })).toBeVisible();
    expect(screen.queryByText("Student")).not.toBeInTheDocument();
  });

  it("shows the bio and the interests", () => {
    signIn({
      bio: "Coastal flood mapping.",
      research_interests: ["GIS", "Remote sensing"],
    });
    renderScreen(<ProfilePage />, { route: "/profile" });

    expect(screen.getByText("Coastal flood mapping.")).toBeVisible();
    const interests = screen.getByRole("list", { name: "Research interests" });
    expect(interests).toHaveTextContent("GIS");
    expect(interests).toHaveTextContent("Remote sensing");
  });

  it("leaves out what was left empty, with no placeholder", () => {
    renderScreen(<ProfilePage />, { route: "/profile" });

    expect(screen.queryByRole("heading", { name: "About" })).not.toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Research interests" })).not.toBeInTheDocument();
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

  it("confirms a save it was sent back from, and otherwise says nothing", () => {
    const { unmount } = renderScreen(<ProfilePage />, { route: "/profile" });
    expect(screen.queryByText("Profile saved.")).not.toBeInTheDocument();
    unmount();

    renderScreen(<ProfilePage />, { route: "/profile", state: { saved: true } });
    expect(screen.getByText("Profile saved.")).toHaveAttribute("role", "status");
  });

  it("has no blocking accessibility violations", async () => {
    signIn({ bio: "Floods.", research_interests: ["GIS"] });
    const { container } = renderScreen(<ProfilePage />, { route: "/profile" });

    await expectNoBlockingA11yViolations(container);
  });
});
