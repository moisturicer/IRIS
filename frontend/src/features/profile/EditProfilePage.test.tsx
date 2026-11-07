/**
 * Edit profile (IR-933; the fields are IR-699's), asserted through the
 * accessible tree. `profileApi` is mocked at its module boundary: it is the
 * one place the IR-695 contract lives, so these tests pin what is sent. One
 * Save sends the name and the profile fields, then returns to the Profile.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, waitFor } from "@testing-library/react";

import { profileApi } from "@/api/profile";
import { useAuthStore } from "@/store/auth.store";
import { expectNoBlockingA11yViolations } from "@/test/axe";
import { Route, Routes, useLocation } from "react-router-dom";

import { authApi } from "@/api/auth";
import { renderScreen, screen, userEvent, within } from "@/test/render";

import EditProfilePage from "./EditProfilePage";

const baseUser = {
  id: 7, email: "ana@cit.edu", first_name: "Ana", middle_initial: "", last_name: "Reyes",
  role_name: "Student", college_name: "CCS", department_name: "", course_name: "",
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
  vi.spyOn(profileApi, "suggestInterests").mockResolvedValue({ data: [] } as never);
  vi.stubGlobal("URL", Object.assign(URL, {
    createObjectURL: vi.fn().mockReturnValue("blob:photo"),
    revokeObjectURL: vi.fn(),
  }));
});

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

/** What the Profile receives on return: the saved flag the real page shows. */
function ProfileStandIn() {
  const saved = (useLocation().state as { saved?: boolean } | null)?.saved;
  return <><h1>Your profile</h1>{saved && <p role="status">Profile saved.</p>}</>;
}

/** The edit page, and a stand-in for the Profile it returns to. */
const withProfile = () => (
  <Routes>
    <Route path="/profile/edit" element={<EditProfilePage />} />
    <Route path="/profile" element={<ProfileStandIn />} />
  </Routes>
);

const aboutYou = () => screen.getByRole("region", { name: "About you" });

describe("bio", () => {
  it("counts characters against the 500 allowed", async () => {
    const user = userEvent.setup();
    renderScreen(<EditProfilePage />, { route: "/profile/edit" });

    await user.type(screen.getByLabelText("Bio"), "Coastal floods");

    expect(screen.getByLabelText("Bio")).toHaveAccessibleDescription(/14 \/ 500 characters/);
  });
});

describe("research interests", () => {
  it("adds an interest, offers suggestions, and removes one", async () => {
    const user = userEvent.setup();
    vi.mocked(profileApi.suggestInterests).mockResolvedValue({ data: ["Machine Learning"] } as never);
    renderScreen(<EditProfilePage />, { route: "/profile/edit" });

    await user.type(screen.getByLabelText("Research interests"), "GIS{Enter}");
    expect(within(aboutYou()).getByRole("button", { name: "Remove GIS" })).toBeVisible();

    await user.type(screen.getByLabelText("Research interests"), "mach");
    await user.click(await screen.findByRole("button", { name: "Add Machine Learning" }));
    expect(profileApi.suggestInterests).toHaveBeenLastCalledWith("mach");
    expect(screen.getByRole("button", { name: "Remove Machine Learning" })).toBeVisible();

    await user.click(screen.getByRole("button", { name: "Remove GIS" }));
    expect(screen.queryByRole("button", { name: "Remove GIS" })).not.toBeInTheDocument();
  });

  it("stops at ten", async () => {
    signIn({ research_interests: Array.from({ length: 10 }, (_, i) => `Topic ${i + 1}`) });
    renderScreen(<EditProfilePage />, { route: "/profile/edit" });

    expect(screen.getByLabelText("Research interests")).toBeDisabled();
    expect(screen.getByText("You've added the 10 interests allowed.")).toBeVisible();
  });

  it("does not add the same interest twice, whatever its case", async () => {
    const user = userEvent.setup();
    signIn({ research_interests: ["GIS"] });
    renderScreen(<EditProfilePage />, { route: "/profile/edit" });

    await user.type(screen.getByLabelText("Research interests"), "gis{Enter}");

    expect(screen.getAllByRole("button", { name: /^Remove GIS$/i })).toHaveLength(1);
  });
});

describe("saving", () => {
  it("sends the profile fields and returns to the Profile", async () => {
    const user = userEvent.setup();
    vi.spyOn(profileApi, "updateFields").mockImplementation(async (fields) =>
      ({ data: { ...baseUser, ...fields } }) as never);
    const { container } = renderScreen(withProfile(), { route: "/profile/edit" });

    await user.type(screen.getByLabelText("Bio"), "Floods.");
    await user.type(screen.getByLabelText("Research interests"), "GIS{Enter}");
    await expectNoBlockingA11yViolations(container);
    await user.click(screen.getByRole("button", { name: "Save" }));

    expect(profileApi.updateFields).toHaveBeenCalledWith({ bio: "Floods.", research_interests: ["GIS"] });
    expect(await screen.findByRole("heading", { name: "Your profile" })).toBeVisible();
    expect(screen.getByRole("status")).toHaveTextContent("Profile saved.");
    expect(useAuthStore.getState().user?.bio).toBe("Floods.");
  });

  it("shows the server's message when it refuses a field", async () => {
    const user = userEvent.setup();
    vi.spyOn(profileApi, "updateFields").mockRejectedValue({
      response: { status: 400, data: { research_interests: ["Keep each interest to 40 characters or fewer."] } },
    });
    renderScreen(<EditProfilePage />, { route: "/profile/edit" });

    await user.type(screen.getByLabelText("Bio"), "x");
    await user.click(screen.getByRole("button", { name: "Save" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Keep each interest to 40 characters or fewer.",
    );
  });

  it("says every field the server refused, including a list's per-item message", async () => {
    const user = userEvent.setup();
    vi.spyOn(profileApi, "updateFields").mockRejectedValue({
      response: {
        status: 400,
        data: {
          bio: ["Keep your bio to 500 characters or fewer."],
          research_interests: { 0: ["Keep each interest to 40 characters or fewer."] },
        },
      },
    });
    renderScreen(<EditProfilePage />, { route: "/profile/edit" });

    await user.type(screen.getByLabelText("Bio"), "x");
    await user.click(screen.getByRole("button", { name: "Save" }));

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("Keep your bio to 500 characters or fewer.");
    expect(alert).toHaveTextContent("Keep each interest to 40 characters or fewer.");
  });
});

describe("name", () => {
  it("sends a changed name and returns to the Profile", async () => {
    const user = userEvent.setup();
    vi.spyOn(authApi, "updateMe").mockResolvedValue({ data: { ...baseUser, first_name: "Anna" } } as never);
    renderScreen(withProfile(), { route: "/profile/edit" });

    await user.clear(screen.getByLabelText("First name"));
    await user.type(screen.getByLabelText("First name"), "Anna");
    await user.click(screen.getByRole("button", { name: "Save" }));

    expect(authApi.updateMe).toHaveBeenCalledWith({ first_name: "Anna", last_name: "Reyes" });
    expect(await screen.findByRole("heading", { name: "Your profile" })).toBeVisible();
    expect(useAuthStore.getState().user?.first_name).toBe("Anna");
  });

  it("requires a first and a last name", async () => {
    const user = userEvent.setup();
    vi.spyOn(authApi, "updateMe");
    renderScreen(<EditProfilePage />, { route: "/profile/edit" });

    await user.clear(screen.getByLabelText("First name"));
    await user.click(screen.getByRole("button", { name: "Save" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("First and last name are required.");
    expect(authApi.updateMe).not.toHaveBeenCalled();
  });

  it("shows the affiliation as the university recorded it, and does not let it be edited", () => {
    signIn({ college_name: "CCS", course_name: "BSCS" });
    renderScreen(<EditProfilePage />, { route: "/profile/edit" });

    expect(screen.getByLabelText("Affiliation")).toHaveAttribute("readonly");
    expect(screen.getByLabelText("Affiliation")).toHaveValue("CCS · BSCS");
  });
});

describe("what is not edited here", () => {
  it("has no middle initial or ORCID iD field, and leaves a recorded middle initial alone", async () => {
    const user = userEvent.setup();
    signIn({ middle_initial: "L" });
    vi.spyOn(authApi, "updateMe").mockResolvedValue({ data: { ...baseUser, first_name: "Anna" } } as never);
    renderScreen(<EditProfilePage />, { route: "/profile/edit" });

    expect(screen.queryByLabelText("M.I.")).not.toBeInTheDocument();
    expect(screen.queryByLabelText("ORCID iD")).not.toBeInTheDocument();

    await user.clear(screen.getByLabelText("First name"));
    await user.type(screen.getByLabelText("First name"), "Anna");
    await user.click(screen.getByRole("button", { name: "Save" }));

    // The initial is not sent, so saving the name cannot change or clear it.
    expect(authApi.updateMe).toHaveBeenCalledWith({ first_name: "Anna", last_name: "Reyes" });
  });
});

describe("leaving", () => {
  it("Save waits for a change", () => {
    renderScreen(<EditProfilePage />, { route: "/profile/edit" });

    expect(screen.getByRole("button", { name: "Save" })).toBeDisabled();
  });

  it("Cancel goes back to the Profile without saving", async () => {
    const user = userEvent.setup();
    vi.spyOn(profileApi, "updateFields");
    renderScreen(withProfile(), { route: "/profile/edit" });

    await user.type(screen.getByLabelText("Bio"), "Not kept");
    await user.click(screen.getByRole("link", { name: "Cancel" }));

    expect(await screen.findByRole("heading", { name: "Your profile" })).toBeVisible();
    expect(profileApi.updateFields).not.toHaveBeenCalled();
  });
});

describe("photo", () => {
  async function choosePhoto(user: ReturnType<typeof userEvent.setup>) {
    const file = new File(["png"], "me.png", { type: "image/png" });
    await user.upload(screen.getByLabelText("Upload photo"), file);
    const dialog = await screen.findByRole("dialog", { name: "Crop your photo" });
    const preview = within(dialog).getByRole("img", { name: "Your photo, as it will appear" });
    Object.defineProperty(preview, "naturalWidth", { value: 1000 });
    Object.defineProperty(preview, "naturalHeight", { value: 500 });
    fireEvent.load(preview);
    return { file, dialog };
  }

  it("crops the chosen photo to a circle and uploads the framed square", async () => {
    const user = userEvent.setup();
    vi.spyOn(profileApi, "uploadPhoto").mockResolvedValue({ data: { photo_url: "/users/7/photo/?v=2" } } as never);
    vi.spyOn(profileApi, "photo").mockResolvedValue({ data: new Blob(["png"]) } as never);
    const { container } = renderScreen(<EditProfilePage />, { route: "/profile/edit" });

    const { file, dialog } = await choosePhoto(user);
    expect(within(dialog).getByRole("slider", { name: "Zoom" })).toBeVisible();
    await expectNoBlockingA11yViolations(container);
    await user.click(within(dialog).getByRole("button", { name: "Use photo" }));

    expect(profileApi.uploadPhoto).toHaveBeenCalledWith(file, { x: 250, y: 0, size: 500 });
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    expect(useAuthStore.getState().user?.photo_url).toBe("/users/7/photo/?v=2");
  });

  it("moves the framing with the arrow keys", async () => {
    const user = userEvent.setup();
    vi.spyOn(profileApi, "uploadPhoto").mockResolvedValue({ data: { photo_url: "/users/7/photo/?v=2" } } as never);
    vi.spyOn(profileApi, "photo").mockResolvedValue({ data: new Blob(["png"]) } as never);
    renderScreen(<EditProfilePage />, { route: "/profile/edit" });

    const { file, dialog } = await choosePhoto(user);
    within(dialog).getByRole("group", { name: /Drag or use the arrow keys/ }).focus();
    await user.keyboard("{ArrowRight}");
    await user.click(within(dialog).getByRole("button", { name: "Use photo" }));

    // Each arrow press moves the framing 10 screen px. The dialog's square is
    // 256 px, so on this 500 px-tall photo one screen px is 500 / 256 image px:
    // the square lands 19.5 px further along the photo, rounded to 270.
    expect(profileApi.uploadPhoto).toHaveBeenCalledWith(file, { x: 270, y: 0, size: 500 });
  });

  it("shows the server's message when it refuses the photo", async () => {
    const user = userEvent.setup();
    vi.spyOn(profileApi, "uploadPhoto").mockRejectedValue({
      response: { status: 400, data: { photo: ["The photo must be 2 MB or smaller."] } },
    });
    renderScreen(<EditProfilePage />, { route: "/profile/edit" });

    const { dialog } = await choosePhoto(user);
    await user.click(within(dialog).getByRole("button", { name: "Use photo" }));

    expect(await within(dialog).findByRole("alert")).toHaveTextContent("The photo must be 2 MB or smaller.");
  });

  it("removes the photo", async () => {
    const user = userEvent.setup();
    signIn({ photo_url: "/users/7/photo/?v=1" });
    vi.spyOn(profileApi, "photo").mockResolvedValue({ data: new Blob(["png"]) } as never);
    vi.spyOn(profileApi, "removePhoto").mockResolvedValue({} as never);
    renderScreen(<EditProfilePage />, { route: "/profile/edit" });

    expect(await screen.findByRole("img", { name: "Your profile photo" })).toBeVisible();
    await user.click(screen.getByRole("button", { name: "Remove photo" }));

    expect(profileApi.removePhoto).toHaveBeenCalled();
    await waitFor(() => expect(useAuthStore.getState().user?.photo_url).toBeNull());
    expect(screen.queryByRole("button", { name: "Remove photo" })).not.toBeInTheDocument();
  });
});
