/**
 * Settings' Profile tab (IR-1304; the form was IR-933's Edit profile page, the
 * fields IR-699's), asserted through the accessible tree. `profileApi` is mocked
 * at its module boundary: it is the one place the IR-695 contract lives, so these
 * tests pin what is sent. One Save sends the name and the profile fields, and the
 * person stays on the tab.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, waitFor } from "@testing-library/react";

import { profileApi } from "@/api/profile";
import { useAuthStore } from "@/store/auth.store";
import { expectNoBlockingA11yViolations } from "@/test/axe";

import { authApi } from "@/api/auth";
import { renderScreen, screen, userEvent, within } from "@/test/render";

import SettingsPage from "./SettingsPage";

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

const renderTab = () => renderScreen(<SettingsPage />, { route: "/settings?tab=profile" });

const aboutYou = () => screen.getByRole("region", { name: "About you" });
const save = () => screen.getByRole("button", { name: "Save" });
const discard = () => screen.getByRole("button", { name: "Discard changes" });

describe("the tab", () => {
  it("is the first Settings section and holds the edit form", () => {
    renderTab();

    const tabs = within(screen.getByRole("navigation", { name: "Settings sections" })).getAllByRole("button");
    expect(tabs[0]).toHaveAccessibleName("Profile");
    expect(tabs[0]).toHaveAttribute("aria-current", "page");
    expect(screen.getByLabelText("First name")).toHaveValue("Ana");
    expect(screen.getByLabelText("Bio")).toBeVisible();
  });

  it("is the section Settings opens on when the address names none", () => {
    renderScreen(<SettingsPage />, { route: "/settings" });

    expect(screen.getByLabelText("First name")).toBeVisible();
  });
});

describe("bio", () => {
  it("counts characters against the 500 allowed", async () => {
    const user = userEvent.setup();
    renderTab();

    await user.type(screen.getByLabelText("Bio"), "Coastal floods");

    expect(screen.getByLabelText("Bio")).toHaveAccessibleDescription(/14 \/ 500 characters/);
  });
});

describe("research interests", () => {
  it("adds an interest, offers suggestions, and removes one", async () => {
    const user = userEvent.setup();
    vi.mocked(profileApi.suggestInterests).mockResolvedValue({ data: ["Machine Learning"] } as never);
    renderTab();

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
    renderTab();

    expect(screen.getByLabelText("Research interests")).toBeDisabled();
    expect(screen.getByText("You've added the 10 interests allowed.")).toBeVisible();
  });

  it("does not add the same interest twice, whatever its case", async () => {
    const user = userEvent.setup();
    signIn({ research_interests: ["GIS"] });
    renderTab();

    await user.type(screen.getByLabelText("Research interests"), "gis{Enter}");

    expect(screen.getAllByRole("button", { name: /^Remove GIS$/i })).toHaveLength(1);
  });
});

describe("saving", () => {
  it("sends the profile fields, stays on the tab, and says it saved with a way to the Profile", async () => {
    const user = userEvent.setup();
    vi.spyOn(profileApi, "updateFields").mockImplementation(async (fields) =>
      ({ data: { ...baseUser, ...fields } }) as never);
    const { container } = renderTab();

    expect(screen.queryByText("Profile saved.")).not.toBeInTheDocument();
    await user.type(screen.getByLabelText("Bio"), "Floods.");
    await user.type(screen.getByLabelText("Research interests"), "GIS{Enter}");
    await expectNoBlockingA11yViolations(container);
    await user.click(save());

    expect(profileApi.updateFields).toHaveBeenCalledWith({ bio: "Floods.", research_interests: ["GIS"] });
    expect(await screen.findByRole("status")).toHaveTextContent("Profile saved.");
    expect(screen.getByRole("link", { name: "View your profile" })).toHaveAttribute("href", "/profile");
    // Still the tab, with what was saved in it, and nothing left to save.
    expect(screen.getByLabelText("Bio")).toHaveValue("Floods.");
    expect(save()).toBeDisabled();
    expect(useAuthStore.getState().user?.bio).toBe("Floods.");
  });

  it("stops saying it saved once the form changes again", async () => {
    const user = userEvent.setup();
    vi.spyOn(profileApi, "updateFields").mockImplementation(async (fields) =>
      ({ data: { ...baseUser, ...fields } }) as never);
    renderTab();

    await user.type(screen.getByLabelText("Bio"), "Floods.");
    await user.click(save());
    await screen.findByText("Profile saved.");
    await user.type(screen.getByLabelText("Bio"), " More.");

    expect(screen.queryByText("Profile saved.")).not.toBeInTheDocument();
    expect(save()).toBeEnabled();
  });

  it("shows the server's message when it refuses a field", async () => {
    const user = userEvent.setup();
    vi.spyOn(profileApi, "updateFields").mockRejectedValue({
      response: { status: 400, data: { research_interests: ["Keep each interest to 40 characters or fewer."] } },
    });
    renderTab();

    await user.type(screen.getByLabelText("Bio"), "x");
    await user.click(save());

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Keep each interest to 40 characters or fewer.",
    );
    expect(screen.queryByText("Profile saved.")).not.toBeInTheDocument();
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
    renderTab();

    await user.type(screen.getByLabelText("Bio"), "x");
    await user.click(save());

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("Keep your bio to 500 characters or fewer.");
    expect(alert).toHaveTextContent("Keep each interest to 40 characters or fewer.");
  });
});

describe("name", () => {
  it("sends a changed name and stays on the tab", async () => {
    const user = userEvent.setup();
    vi.spyOn(authApi, "updateMe").mockResolvedValue({ data: { ...baseUser, first_name: "Anna" } } as never);
    renderTab();

    await user.clear(screen.getByLabelText("First name"));
    await user.type(screen.getByLabelText("First name"), "Anna");
    await user.click(save());

    expect(authApi.updateMe).toHaveBeenCalledWith({ first_name: "Anna", last_name: "Reyes" });
    expect(await screen.findByText("Profile saved.")).toBeVisible();
    expect(screen.getByLabelText("First name")).toHaveValue("Anna");
    expect(useAuthStore.getState().user?.first_name).toBe("Anna");
  });

  it("requires a first and a last name", async () => {
    const user = userEvent.setup();
    vi.spyOn(authApi, "updateMe");
    renderTab();

    await user.clear(screen.getByLabelText("First name"));
    await user.click(save());

    expect(await screen.findByRole("alert")).toHaveTextContent("First and last name are required.");
    expect(authApi.updateMe).not.toHaveBeenCalled();
  });

  it("shows the affiliation as the university recorded it, and does not let it be edited", () => {
    signIn({ college_name: "CCS", course_name: "BSCS" });
    renderTab();

    expect(screen.getByLabelText("Affiliation")).toHaveAttribute("readonly");
    expect(screen.getByLabelText("Affiliation")).toHaveValue("CCS · BSCS");
  });
});

describe("what is not edited here", () => {
  it("has no middle initial or ORCID iD field, and leaves a recorded middle initial alone", async () => {
    const user = userEvent.setup();
    signIn({ middle_initial: "L" });
    vi.spyOn(authApi, "updateMe").mockResolvedValue({ data: { ...baseUser, first_name: "Anna" } } as never);
    renderTab();

    expect(screen.queryByLabelText("M.I.")).not.toBeInTheDocument();
    expect(screen.queryByLabelText("ORCID iD")).not.toBeInTheDocument();

    await user.clear(screen.getByLabelText("First name"));
    await user.type(screen.getByLabelText("First name"), "Anna");
    await user.click(save());

    // The initial is not sent, so saving the name cannot change or clear it.
    expect(authApi.updateMe).toHaveBeenCalledWith({ first_name: "Anna", last_name: "Reyes" });
  });
});

describe("discarding", () => {
  it("Save and Discard changes both wait for a change", () => {
    renderTab();

    expect(save()).toBeDisabled();
    expect(discard()).toBeDisabled();
  });

  it("Discard changes puts back what was saved, and sends nothing", async () => {
    const user = userEvent.setup();
    signIn({ bio: "Saved bio", research_interests: ["GIS"] });
    vi.spyOn(profileApi, "updateFields");
    vi.spyOn(authApi, "updateMe");
    renderTab();

    await user.clear(screen.getByLabelText("First name"));
    await user.type(screen.getByLabelText("First name"), "Anna");
    await user.type(screen.getByLabelText("Bio"), " and more");
    await user.click(screen.getByRole("button", { name: "Remove GIS" }));
    expect(discard()).toBeEnabled();
    await user.click(discard());

    expect(screen.getByLabelText("First name")).toHaveValue("Ana");
    expect(screen.getByLabelText("Bio")).toHaveValue("Saved bio");
    expect(screen.getByRole("button", { name: "Remove GIS" })).toBeVisible();
    expect(save()).toBeDisabled();
    expect(discard()).toBeDisabled();
    expect(profileApi.updateFields).not.toHaveBeenCalled();
    expect(authApi.updateMe).not.toHaveBeenCalled();
  });

  it("Discard changes clears an error from a refused save", async () => {
    const user = userEvent.setup();
    vi.spyOn(profileApi, "updateFields").mockRejectedValue({
      response: { status: 400, data: { bio: ["Keep your bio to 500 characters or fewer."] } },
    });
    renderTab();

    await user.type(screen.getByLabelText("Bio"), "x");
    await user.click(save());
    await screen.findByRole("alert");
    await user.click(discard());

    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
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

  it("crops the chosen photo to a circle and uploads the framed square with Save", async () => {
    const user = userEvent.setup();
    vi.spyOn(profileApi, "uploadPhoto").mockResolvedValue({ data: { photo_url: "/users/7/photo/?v=2" } } as never);
    vi.spyOn(profileApi, "updateFields");
    vi.spyOn(authApi, "updateMe");
    const { container } = renderTab();

    expect(save()).toBeDisabled();
    const { file, dialog } = await choosePhoto(user);
    expect(within(dialog).getByRole("slider", { name: "Zoom" })).toBeVisible();
    await expectNoBlockingA11yViolations(container);
    await user.click(within(dialog).getByRole("button", { name: "Use photo" }));

    // Framed and shown, but not sent until Save.
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    expect(screen.getByRole("img", { name: "Your profile photo" })).toBeVisible();
    expect(profileApi.uploadPhoto).not.toHaveBeenCalled();
    expect(save()).toBeEnabled();

    await user.click(save());

    expect(profileApi.uploadPhoto).toHaveBeenCalledWith(file, { x: 250, y: 0, size: 500 });
    expect(await screen.findByText("Profile saved.")).toBeVisible();
    expect(useAuthStore.getState().user?.photo_url).toBe("/users/7/photo/?v=2");
    // Only the photo changed, so nothing else is sent.
    expect(profileApi.updateFields).not.toHaveBeenCalled();
    expect(authApi.updateMe).not.toHaveBeenCalled();
  });

  it("Discard changes leaves the old photo: a cropped photo is not uploaded", async () => {
    const user = userEvent.setup();
    vi.spyOn(profileApi, "uploadPhoto");
    renderTab();

    const { dialog } = await choosePhoto(user);
    await user.click(within(dialog).getByRole("button", { name: "Use photo" }));
    await user.click(discard());

    expect(screen.queryByRole("img", { name: "Your profile photo" })).not.toBeInTheDocument();
    expect(save()).toBeDisabled();
    expect(profileApi.uploadPhoto).not.toHaveBeenCalled();
    expect(useAuthStore.getState().user?.photo_url).toBeNull();
  });

  it("moves the framing with the arrow keys", async () => {
    const user = userEvent.setup();
    vi.spyOn(profileApi, "uploadPhoto").mockResolvedValue({ data: { photo_url: "/users/7/photo/?v=2" } } as never);
    renderTab();

    const { file, dialog } = await choosePhoto(user);
    within(dialog).getByRole("group", { name: /Drag or use the arrow keys/ }).focus();
    await user.keyboard("{ArrowRight}");
    await user.click(within(dialog).getByRole("button", { name: "Use photo" }));
    await user.click(save());

    // Each arrow press moves the framing 10 screen px. The dialog's square is
    // 256 px, so on this 500 px-tall photo one screen px is 500 / 256 image px:
    // the square lands 19.5 px further along the photo, rounded to 270.
    expect(profileApi.uploadPhoto).toHaveBeenCalledWith(file, { x: 270, y: 0, size: 500 });
  });

  it("shows the server's message when it refuses the photo, and stays on the tab", async () => {
    const user = userEvent.setup();
    vi.spyOn(profileApi, "uploadPhoto").mockRejectedValue({
      response: { status: 400, data: { photo: ["The photo must be 2 MB or smaller."] } },
    });
    renderTab();

    const { dialog } = await choosePhoto(user);
    await user.click(within(dialog).getByRole("button", { name: "Use photo" }));
    await user.click(save());

    expect(await screen.findByRole("alert")).toHaveTextContent("The photo must be 2 MB or smaller.");
    expect(save()).toBeEnabled();
  });

  it("removes the photo with Save", async () => {
    const user = userEvent.setup();
    signIn({ photo_url: "/users/7/photo/?v=1" });
    vi.spyOn(profileApi, "photo").mockResolvedValue({ data: new Blob(["png"]) } as never);
    vi.spyOn(profileApi, "removePhoto").mockResolvedValue({} as never);
    renderTab();

    expect(await screen.findByRole("img", { name: "Your profile photo" })).toBeVisible();
    await user.click(screen.getByRole("button", { name: "Remove photo" }));

    expect(screen.queryByRole("img", { name: "Your profile photo" })).not.toBeInTheDocument();
    expect(profileApi.removePhoto).not.toHaveBeenCalled();
    await user.click(save());

    expect(profileApi.removePhoto).toHaveBeenCalled();
    await waitFor(() => expect(useAuthStore.getState().user?.photo_url).toBeNull());
  });

  it("Discard changes keeps the photo a person chose to remove", async () => {
    const user = userEvent.setup();
    signIn({ photo_url: "/users/7/photo/?v=1" });
    vi.spyOn(profileApi, "photo").mockResolvedValue({ data: new Blob(["png"]) } as never);
    vi.spyOn(profileApi, "removePhoto");
    renderTab();

    await user.click(await screen.findByRole("button", { name: "Remove photo" }));
    await user.click(discard());

    expect(await screen.findByRole("img", { name: "Your profile photo" })).toBeVisible();
    expect(profileApi.removePhoto).not.toHaveBeenCalled();
    expect(useAuthStore.getState().user?.photo_url).toBe("/users/7/photo/?v=1");
  });
});
