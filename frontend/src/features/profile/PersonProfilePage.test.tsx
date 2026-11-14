/**
 * Another person's Profile (IR-700): what a reader sees, what is left out, how
 * a long list pages, what a failure looks like, and where a hidden or
 * your-own profile goes. Asserted through the accessible tree. `peopleApi` is
 * mocked at its module boundary: it is the one place the draft IR-696 contract
 * lives, so these tests pin what is asked for.
 */
import { Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { peopleApi } from "@/api/people";
import { profileApi } from "@/api/profile";
import { RequestTimeoutError } from "@/api/requestPolicy";
import { useAuthStore } from "@/store/auth.store";
import { expectNoBlockingA11yViolations } from "@/test/axe";
import { renderScreen, screen, userEvent, waitFor, within } from "@/test/render";
import type { Collaborator, ProfilePaper, PublicProfile } from "@/types/people";

import PersonProfilePage from "./PersonProfilePage";

const person: PublicProfile = {
  id: 101, first_name: "Marites", middle_initial: "C", last_name: "Villanueva", role_label: "Adviser",
  college_name: "College of Engineering and Architecture", department_name: "Department of Computer Engineering",
  course_name: "", bio: "I work on how communities in Cebu prepare for flooding.",
  research_interests: ["Flood risk", "GIS"], photo_url: null,
};

const paper = (id: number, over: Partial<ProfilePaper> = {}): ProfilePaper => ({
  id, title: `Paper ${id}`, authors: ["Reyes, A.", "Villanueva, M."], classification_name: "Geomatics",
  record_type_name: "Thesis / Research", publication_year: 2025, views: 48, ...over,
});

const collaborator = (id: number, over: Partial<Collaborator> = {}): Collaborator => ({
  id, first_name: "Ana", middle_initial: "L", last_name: `Reyes${id}`, photo_url: null, shared_papers: 14, ...over,
});

const page = <T,>(results: T[], more = false) => ({ data: { results, next: more ? "next" : null } }) as never;

/** Stub every call; pass what a test cares about. */
function serve(over: {
  person?: unknown; research?: unknown; advised?: unknown; collaborators?: unknown;
} = {}) {
  vi.spyOn(peopleApi, "get").mockImplementation((over.person as never) ?? (() => Promise.resolve({ data: person }) as never));
  vi.spyOn(peopleApi, "research").mockImplementation((over.research as never) ?? (() => Promise.resolve(page([paper(500)])) as never));
  vi.spyOn(peopleApi, "advised").mockImplementation((over.advised as never) ?? (() => Promise.resolve(page([paper(600)])) as never));
  vi.spyOn(peopleApi, "collaborators").mockImplementation((over.collaborators as never) ?? (() => Promise.resolve(page([collaborator(201)])) as never));
}

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
  vi.stubGlobal("URL", Object.assign(URL, {
    createObjectURL: vi.fn().mockReturnValue("blob:photo"),
    revokeObjectURL: vi.fn(),
  }));
});

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

const notFound = (status = 404) => () => Promise.reject({ response: { status, data: {} } });

describe("a full profile", () => {
  it("names the person, their role, affiliation and the university", async () => {
    serve();
    open(101);

    expect(await screen.findByRole("heading", { level: 1, name: "Marites C. Villanueva" })).toBeVisible();
    expect(screen.getByText("Adviser")).toBeVisible();
    expect(screen.getByText("College of Engineering and Architecture · Department of Computer Engineering")).toBeVisible();
    expect(screen.getByText("Cebu Institute of Technology – University")).toBeVisible();
    expect(peopleApi.get).toHaveBeenCalledWith(101);
  });

  it("shows About, interests, Research, Advised and Collaborators, with no totals in a heading", async () => {
    serve();
    open(101);

    for (const name of ["About", "Research interests", "Research", "Advised", "Collaborators"]) {
      expect(await screen.findByRole("heading", { level: 2, name })).toBeVisible();
    }
    expect(screen.getByRole("list", { name: "Research interests" })).toHaveTextContent("Flood risk");
  });

  it("asks for the first page of each list at the settled size", async () => {
    serve();
    open(101);
    await screen.findByRole("heading", { level: 1 });

    expect(peopleApi.research).toHaveBeenCalledWith(101, 1);
    expect(peopleApi.advised).toHaveBeenCalledWith(101, 1);
    expect(peopleApi.collaborators).toHaveBeenCalledWith(101, 1);
  });

  it("gives each paper its own views, linked to the paper", async () => {
    serve();
    open(101);
    const research = await screen.findByRole("list", { name: "Research" });

    const first = within(research).getAllByRole("listitem")[0];
    expect(within(first).getByRole("link", { name: "Paper 500" })).toHaveAttribute("href", "/records/500");
    expect(first).toHaveTextContent("48 views");
  });

  it("never prints an email address or a citation count", async () => {
    serve();
    const { container } = open(101);
    await screen.findByRole("heading", { level: 1 });

    expect(container.textContent).not.toMatch(/@/);
    expect(container.textContent).not.toMatch(/citation|h-index|follower/i);
  });

  it("links each collaborator to their profile, with the papers they shared", async () => {
    serve();
    open(101);
    const rail = await screen.findByRole("complementary", { name: "Collaborators" });

    expect(within(rail).getByRole("link", { name: "Ana L. Reyes201" })).toHaveAttribute("href", "/people/201");
    expect(rail).toHaveTextContent("14 shared papers");
  });

  it("fetches the photo with auth, and falls back to initials when there is none", async () => {
    vi.spyOn(profileApi, "photo").mockResolvedValue({ data: new Blob(["png"]) } as never);
    serve({ person: () => Promise.resolve({ data: { ...person, photo_url: "/users/101/photo/?v=1" } }) });
    open(101);

    expect(await screen.findByRole("img", { name: "Marites C. Villanueva" })).toBeVisible();
    expect(profileApi.photo).toHaveBeenCalledWith("/users/101/photo/?v=1");
  });

  it("has no blocking accessibility violations", async () => {
    serve();
    const { container } = open(101);
    await screen.findByRole("heading", { level: 1 });

    await expectNoBlockingA11yViolations(container);
  });
});

describe("long lists", () => {
  const first = Array.from({ length: 10 }, (_, i) => paper(700 + i));
  const second = Array.from({ length: 4 }, (_, i) => paper(710 + i));

  it("offers Show more while the server has a next page, and puts focus on the first new paper", async () => {
    const advised = vi.fn().mockImplementation((_id: number, n: number) =>
      Promise.resolve(n === 1 ? page(first, true) : page(second)));
    serve({ advised });
    open(101);
    const list = await screen.findByRole("list", { name: "Advised" });
    expect(within(list).getAllByRole("listitem")).toHaveLength(10);

    await userEvent.click(screen.getByRole("button", { name: "Show more advised papers" }));

    await waitFor(() => expect(within(list).getAllByRole("listitem")).toHaveLength(14));
    expect(advised).toHaveBeenLastCalledWith(101, 2);
    expect(within(within(list).getAllByRole("listitem")[10]).getByRole("link")).toHaveFocus();
    expect(screen.queryByRole("button", { name: "Show more advised papers" })).not.toBeInTheDocument();
  });

  it("pages Collaborators on their own", async () => {
    const collaborators = vi.fn().mockImplementation((_id: number, n: number) =>
      Promise.resolve(n === 1 ? page([collaborator(1), collaborator(2)], true) : page([collaborator(3)])));
    serve({ collaborators });
    open(101);
    const rail = await screen.findByRole("complementary", { name: "Collaborators" });

    await userEvent.click(within(rail).getByRole("button", { name: "Show more collaborators" }));

    await waitFor(() => expect(within(rail).getAllByRole("listitem")).toHaveLength(3));
    expect(collaborators).toHaveBeenLastCalledWith(101, 2);
  });

  it("does not offer Show more when everything fits", async () => {
    serve();
    open(101);
    await screen.findByRole("heading", { level: 1 });

    expect(screen.queryByRole("button", { name: /Show more/ })).not.toBeInTheDocument();
  });

  it("keeps what is shown when the next page fails, and says so with a retry", async () => {
    const advised = vi.fn()
      .mockResolvedValueOnce(page(first, true))
      .mockRejectedValueOnce({ response: { status: 500, data: {} } })
      .mockResolvedValueOnce(page(second));
    serve({ advised });
    open(101);
    const list = await screen.findByRole("list", { name: "Advised" });

    await userEvent.click(screen.getByRole("button", { name: "Show more advised papers" }));
    expect(await screen.findByRole("alert")).toBeVisible();
    expect(within(list).getAllByRole("listitem")).toHaveLength(10);

    await userEvent.click(screen.getByRole("button", { name: "Try again" }));
    await waitFor(() => expect(within(list).getAllByRole("listitem")).toHaveLength(14));
  });
});

describe("a short or empty profile", () => {
  it("leaves out sections with nothing in them", async () => {
    serve({ advised: () => Promise.resolve(page([])) });
    open(101);

    expect(await screen.findByRole("heading", { level: 2, name: "Research" })).toBeVisible();
    expect(screen.queryByRole("heading", { name: "Advised" })).not.toBeInTheDocument();
  });

  it("says so once when there is nothing published, and shows no empty sections", async () => {
    serve({
      person: () => Promise.resolve({ data: { ...person, bio: "", research_interests: [] } }),
      research: () => Promise.resolve(page([])),
      advised: () => Promise.resolve(page([])),
      collaborators: () => Promise.resolve(page([])),
    });
    open(101);

    expect(await screen.findByText("No published papers yet.")).toBeVisible();
    for (const name of ["About", "Research interests", "Research", "Advised", "Collaborators"]) {
      expect(screen.queryByRole("heading", { name })).not.toBeInTheDocument();
    }
    expect(screen.queryByRole("img")).not.toBeInTheDocument();
  });

  it("names an office as the role, and leaves out an affiliation nobody recorded", async () => {
    serve({
      person: () => Promise.resolve({ data: { ...person, role_label: "RDCO", college_name: "", department_name: "" } }),
    });
    open(101);

    expect(await screen.findByText("RDCO")).toBeVisible();
    expect(screen.queryByText(/College of/)).not.toBeInTheDocument();
  });
});

describe("what the reader may not see", () => {
  it("shows the standard not-found screen for a hidden profile, and does not ask for its lists' content", async () => {
    serve({ person: notFound() });
    open(104);

    expect(await screen.findByRole("heading", { name: "Profile not available" })).toBeVisible();
    expect(screen.getByText("This profile doesn't exist, or it isn't available to you.")).toBeVisible();
    expect(screen.queryByText("Paper 500")).not.toBeInTheDocument();
  });

  it("answers an address that is not an id the same way, without asking the server", () => {
    serve();
    open("abc");

    expect(screen.getByRole("heading", { name: "Profile not available" })).toBeVisible();
    expect(peopleApi.get).not.toHaveBeenCalled();
  });

  it("sends your own id to your own profile, without asking the server", () => {
    serve();
    open(7);

    expect(screen.getByText("Your own profile")).toBeVisible();
    expect(peopleApi.get).not.toHaveBeenCalled();
  });
});

describe("loading and failing", () => {
  it("announces loading once, then shows the profile", async () => {
    serve();
    open(101);

    expect(screen.getByRole("status")).toHaveTextContent("Loading profile…");
    expect(await screen.findByRole("heading", { level: 1 })).toBeVisible();
  });

  it("offers a retry when the profile cannot be read, and reads it again", async () => {
    serve({ person: vi.fn().mockRejectedValueOnce({ response: { status: 500, data: {} } }).mockResolvedValue({ data: person }) });
    open(101);

    expect(await screen.findByRole("alert")).toHaveTextContent("We couldn't load this profile");
    await userEvent.click(screen.getByRole("button", { name: "Try again" }));

    expect(await screen.findByRole("heading", { level: 1, name: "Marites C. Villanueva" })).toBeVisible();
  });

  it("calls a read that got no answer in time interrupted, not refused", async () => {
    serve({ person: () => Promise.reject(new RequestTimeoutError(30_000, "get", "/users/101/profile/")) });
    open(101);

    expect(await screen.findByText("This took too long")).toBeVisible();
    expect(screen.getByRole("button", { name: "Try again" })).toBeVisible();
  });

  it("keeps a failed list in its place with its own retry, and still shows the rest", async () => {
    const research = vi.fn().mockRejectedValueOnce({ response: { status: 500, data: {} } }).mockResolvedValue(page([paper(500)]));
    serve({ research });
    open(101);

    const section = (await screen.findByRole("heading", { level: 2, name: "Research" })).closest("section")!;
    expect(within(section).getByRole("alert")).toBeVisible();
    expect(screen.getByRole("heading", { level: 2, name: "Advised" })).toBeVisible();

    await userEvent.click(within(section).getByRole("button", { name: "Try again" }));
    expect(await screen.findByRole("link", { name: "Paper 500" })).toBeVisible();
    expect(research).toHaveBeenLastCalledWith(101, 1);
  });
});
