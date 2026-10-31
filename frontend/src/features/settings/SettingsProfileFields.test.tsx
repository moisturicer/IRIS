/**
 * The profile fields in Settings & Profile (IR-699), asserted through the
 * accessible tree. `profileApi` is mocked at its module boundary: it is the
 * one place the IR-695 contract lives, so these tests pin what is sent.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, waitFor } from "@testing-library/react";

import { profileApi } from "@/api/profile";
import { useAuthStore } from "@/store/auth.store";
import { expectNoBlockingA11yViolations } from "@/test/axe";
import { renderScreen, screen, userEvent, within } from "@/test/render";

import SettingsPage from "./SettingsPage";

const baseUser = {
  id: 7, email: "ana@cit.edu", first_name: "Ana", middle_initial: "", last_name: "Reyes",
  role_name: "Student", college_name: "CCS", department_name: "", course_name: "",
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

const aboutYou = () => screen.getByRole("region", { name: "About you" });

describe("bio", () => {
  it("counts characters against the 500 allowed", async () => {
    const user = userEvent.setup();
    renderScreen(<SettingsPage />, { route: "/settings" });

    await user.type(screen.getByLabelText("Bio"), "Coastal floods");

    expect(screen.getByLabelText("Bio")).toHaveAccessibleDescription(/14 \/ 500 characters/);
  });
});

describe("research interests", () => {
  it("adds an interest, offers suggestions, and removes one", async () => {
    const user = userEvent.setup();
    vi.mocked(profileApi.suggestInterests).mockResolvedValue({ data: ["Machine Learning"] } as never);
    renderScreen(<SettingsPage />, { route: "/settings" });

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
    renderScreen(<SettingsPage />, { route: "/settings" });

    expect(screen.getByLabelText("Research interests")).toBeDisabled();
    expect(screen.getByText("You've added the 10 interests allowed.")).toBeVisible();
  });

  it("does not add the same interest twice, whatever its case", async () => {
    const user = userEvent.setup();
    signIn({ research_interests: ["GIS"] });
    renderScreen(<SettingsPage />, { route: "/settings" });

    await user.type(screen.getByLabelText("Research interests"), "gis{Enter}");

    expect(screen.getAllByRole("button", { name: /^Remove GIS$/i })).toHaveLength(1);
  });
});

describe("ORCID iD", () => {
  it("checks the iD as you type and will not save a bad one", async () => {
    const user = userEvent.setup();
    renderScreen(<SettingsPage />, { route: "/settings" });

    await user.type(screen.getByLabelText("ORCID iD"), "0000-0002-1825-0098");

    expect(screen.getByLabelText("ORCID iD")).toHaveAttribute("aria-invalid", "true");
    expect(screen.getByLabelText("ORCID iD")).toHaveAccessibleDescription(/doesn't check out/);
    expect(within(aboutYou()).getByRole("button", { name: "Save" })).toBeDisabled();
  });
});

describe("saving", () => {
  it("sends the profile fields and confirms", async () => {
    const user = userEvent.setup();
    vi.spyOn(profileApi, "updateFields").mockImplementation(async (fields) =>
      ({ data: { ...baseUser, ...fields } }) as never);
    const { container } = renderScreen(<SettingsPage />, { route: "/settings" });

    await user.type(screen.getByLabelText("Bio"), "Floods.");
    await user.type(screen.getByLabelText("Research interests"), "GIS{Enter}");
    await user.type(screen.getByLabelText("ORCID iD"), "0000-0002-1825-0097");
    await user.click(within(aboutYou()).getByRole("button", { name: "Save" }));

    expect(profileApi.updateFields).toHaveBeenCalledWith({
      bio: "Floods.", research_interests: ["GIS"], orcid: "0000-0002-1825-0097",
    });
    expect(await within(aboutYou()).findByRole("status")).toHaveTextContent("Profile saved.");
    expect(useAuthStore.getState().user?.bio).toBe("Floods.");
    await expectNoBlockingA11yViolations(container);
  });

  it("clears an emptied ORCID iD as null", async () => {
    const user = userEvent.setup();
    signIn({ orcid: "0000-0002-1825-0097" });
    vi.spyOn(profileApi, "updateFields").mockResolvedValue({ data: baseUser } as never);
    renderScreen(<SettingsPage />, { route: "/settings" });

    await user.clear(screen.getByLabelText("ORCID iD"));
    await user.click(within(aboutYou()).getByRole("button", { name: "Save" }));

    expect(profileApi.updateFields).toHaveBeenCalledWith({ bio: "", research_interests: [], orcid: null });
  });

  it("shows the server's message when it refuses a field", async () => {
    const user = userEvent.setup();
    vi.spyOn(profileApi, "updateFields").mockRejectedValue({
      response: { status: 400, data: { research_interests: ["Keep each interest to 40 characters or fewer."] } },
    });
    renderScreen(<SettingsPage />, { route: "/settings" });

    await user.type(screen.getByLabelText("Bio"), "x");
    await user.click(within(aboutYou()).getByRole("button", { name: "Save" }));

    expect(await within(aboutYou()).findByRole("status")).toHaveTextContent(
      "Keep each interest to 40 characters or fewer.",
    );
  });
});

it("links to your own profile", () => {
  renderScreen(<SettingsPage />, { route: "/settings" });

  expect(screen.getByRole("link", { name: "View my profile" })).toHaveAttribute("href", "/people/7");
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
    const { container } = renderScreen(<SettingsPage />, { route: "/settings" });

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
    renderScreen(<SettingsPage />, { route: "/settings" });

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
    renderScreen(<SettingsPage />, { route: "/settings" });

    const { dialog } = await choosePhoto(user);
    await user.click(within(dialog).getByRole("button", { name: "Use photo" }));

    expect(await within(dialog).findByRole("alert")).toHaveTextContent("The photo must be 2 MB or smaller.");
  });

  it("removes the photo", async () => {
    const user = userEvent.setup();
    signIn({ photo_url: "/users/7/photo/?v=1" });
    vi.spyOn(profileApi, "photo").mockResolvedValue({ data: new Blob(["png"]) } as never);
    vi.spyOn(profileApi, "removePhoto").mockResolvedValue({} as never);
    renderScreen(<SettingsPage />, { route: "/settings" });

    expect(await screen.findByRole("img", { name: "Your profile photo" })).toBeVisible();
    await user.click(screen.getByRole("button", { name: "Remove photo" }));

    expect(profileApi.removePhoto).toHaveBeenCalled();
    await waitFor(() => expect(useAuthStore.getState().user?.photo_url).toBeNull());
    expect(screen.queryByRole("button", { name: "Remove photo" })).not.toBeInTheDocument();
  });
});
