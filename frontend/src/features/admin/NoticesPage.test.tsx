/**
 * The Notices page (ADR-051 decisions 16-17 as amended by ADR-063 decision 9,
 * IR-800): RDCO publishes the next version of the one data notice by pasting
 * it; RDCO and the System Admin read every version.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { noticeApi, type NoticeVersion } from "@/api/notice";
import { ROLES, type RoleName } from "@/lib/constants";
import { useAuthStore } from "@/store/auth.store";
import { expectNoBlockingA11yViolations } from "@/test/axe";
import { makeUser } from "@/test/authFixtures";
import { renderScreen, screen, userEvent, waitFor, within } from "@/test/render";
import NoticesPage from "./NoticesPage";

const RDCO_PERSON = { id: 4, name: "Rita Dela Cruz", email: "rdco@cit.edu" };
const V2: NoticeVersion = {
  version: 2, text: "IRIS data notice\n\nWhat IRIS keeps\nYour name.", published_at: "2026-11-05T02:00:00Z",
  published_by: RDCO_PERSON,
};
const V1: NoticeVersion = {
  version: 1, text: "Interim notice\nWhat IRIS keeps when you register", published_at: "2026-11-01T02:00:00Z",
  published_by: null,
};

function signInAs(role: RoleName) {
  useAuthStore.setState({
    user: makeUser({ role_name: role }), accessToken: "t", isAuthenticated: true, authReady: true,
  });
}

function versions(list: NoticeVersion[] = [V2, V1]) {
  return vi.spyOn(noticeApi, "versions").mockResolvedValue({ data: list } as never);
}

async function openPage() {
  const user = userEvent.setup();
  const view = renderScreen(<NoticesPage />, { route: "/notices" });
  await screen.findByRole("heading", { level: 2, name: "Version history" });
  return { user, ...view };
}

const field = () => screen.getByRole("textbox", { name: "Notice text" });

beforeEach(() => signInAs(ROLES.RDCO));
afterEach(() => vi.restoreAllMocks());

describe("RDCO publishes the next version", () => {
  it("opens on the current version, who published it, and its text ready to replace", async () => {
    versions();
    const { container } = await openPage();

    const current = screen.getByRole("group", { name: "Current version" });
    expect(current).toHaveTextContent("Version 2, published Nov 5, 2026 by Rita Dela Cruz");
    expect(field()).toHaveValue(V2.text);
    const rules = screen.getByRole("note");
    expect(rules).toHaveTextContent(/data protection officer.*approve.*before you publish/i);
    expect(rules).toHaveTextContent(/can't be changed once it is published/);
    await expectNoBlockingA11yViolations(container);
  });

  it("previews the pasted text exactly as readers will see it", async () => {
    versions();
    const { user } = await openPage();

    await user.clear(field());
    await user.click(field());
    await user.paste("New notice\n\n<b>Not bold</b>\nhttps://cit.edu");
    await user.click(screen.getByRole("button", { name: "Preview" }));

    const preview = screen.getByRole("region", { name: "Preview" });
    expect(within(preview).getByText("Version 3 · not published yet")).toBeInTheDocument();
    expect(within(preview).getByText(/^New notice/).textContent).toBe("New notice\n\n<b>Not bold</b>\nhttps://cit.edu");
    expect(within(preview).queryByRole("link")).not.toBeInTheDocument();
  });

  it("asks first, saying how many must answer again, then publishes the paste as the next version", async () => {
    versions();
    vi.spyOn(noticeApi, "impact").mockResolvedValue({ data: { current_version: 2, accounts_to_answer: 41 } } as never);
    const publish = vi.spyOn(noticeApi, "publish").mockResolvedValue({
      data: { ...V2, version: 3, text: "Version three" },
    } as never);
    const { user, container } = await openPage();

    await user.clear(field());
    await user.type(field(), "Version three");
    await user.click(screen.getByRole("button", { name: "Publish version 3" }));

    const dialog = await screen.findByRole("dialog", { name: "Publish version 3?" });
    expect(dialog).toHaveTextContent("41 people must answer it before they can keep using IRIS");
    expect(dialog).toHaveTextContent("can't be changed");
    expect(publish).not.toHaveBeenCalled();
    await expectNoBlockingA11yViolations(container);

    versions([{ ...V2, version: 3, text: "Version three" }, V2, V1]);
    await user.click(within(dialog).getByRole("button", { name: "Publish" }));

    expect(publish).toHaveBeenCalledWith({ based_on_version: 2, text: "Version three" });
    expect(await screen.findByRole("status")).toHaveTextContent("Version 3 is published.");
    await waitFor(() => expect(screen.getByRole("group", { name: "Current version" })).toHaveTextContent("Version 3"));
  });

  it("sends nothing when the confirmation is cancelled", async () => {
    versions();
    vi.spyOn(noticeApi, "impact").mockResolvedValue({ data: { current_version: 2, accounts_to_answer: 1 } } as never);
    const publish = vi.spyOn(noticeApi, "publish");
    const { user } = await openPage();

    await user.type(field(), " edited");
    await user.click(screen.getByRole("button", { name: "Publish version 3" }));
    const dialog = await screen.findByRole("dialog", { name: "Publish version 3?" });
    expect(dialog).toHaveTextContent("1 person must answer it");
    await user.click(within(dialog).getByRole("button", { name: "Cancel" }));

    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(publish).not.toHaveBeenCalled();
    expect(field()).toHaveValue(`${V2.text} edited`);
  });

  it("can't publish the text unchanged or blank", async () => {
    versions();
    const { user } = await openPage();

    expect(screen.getByRole("button", { name: "Publish version 3" })).toBeDisabled();
    await user.clear(field());
    expect(screen.getByRole("button", { name: "Publish version 3" })).toBeDisabled();
  });

  it("says why Publish is unavailable, and stops saying it once the text can be published (IR-1088)", async () => {
    versions();
    const { user } = await openPage();
    const publish = () => screen.getByRole("button", { name: "Publish version 3" });

    expect(publish()).toHaveAccessibleDescription("Change the text to publish a new version.");
    await user.clear(field());
    expect(publish()).toHaveAccessibleDescription("Enter the notice text to publish.");

    await user.click(field());
    await user.paste("A new notice");
    expect(publish()).toBeEnabled();
    expect(publish()).not.toHaveAttribute("aria-describedby");
    expect(publish()).toHaveClass("rounded-full");
  });

  it("shows the server's refusal when a newer version was published meanwhile, and keeps the paste", async () => {
    versions();
    vi.spyOn(noticeApi, "impact").mockResolvedValue({ data: { current_version: 2, accounts_to_answer: 3 } } as never);
    vi.spyOn(noticeApi, "publish").mockRejectedValue({
      response: {
        status: 409,
        data: {
          code: "notice_stale", detail: "A newer data notice was published. Read it before answering.",
          notice: { version: 3, text: "Someone else's", published_at: "2026-11-08T02:00:00Z" },
        },
      },
    });
    const { user } = await openPage();

    await user.clear(field());
    await user.type(field(), "My paste");
    await user.click(screen.getByRole("button", { name: "Publish version 3" }));
    versions([{ ...V2, version: 3, text: "Someone else's" }, V2, V1]);
    await user.click(within(await screen.findByRole("dialog")).getByRole("button", { name: "Publish" }));

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("A newer data notice was published.");
    expect(alert).toHaveTextContent("Version 3 is current now. Read it below before publishing your text as version 4.");
    expect(field()).toHaveValue("My paste");
    expect(await screen.findByRole("button", { name: "Publish version 4" })).toBeEnabled();
  });

  it("keeps the paste and the outcome on screen while the history is read again", async () => {
    versions();
    vi.spyOn(noticeApi, "impact").mockResolvedValue({ data: { current_version: 2, accounts_to_answer: 3 } } as never);
    vi.spyOn(noticeApi, "publish").mockRejectedValue({
      response: {
        status: 409,
        data: { code: "notice_stale", detail: "A newer data notice was published.", notice: { version: 3, text: "x", published_at: null } },
      },
    });
    const { user } = await openPage();

    await user.clear(field());
    await user.type(field(), "My paste");
    await user.click(screen.getByRole("button", { name: "Publish version 3" }));
    // The reread doesn't answer yet: the form must not give way to a spinner meanwhile.
    vi.spyOn(noticeApi, "versions").mockReturnValue(new Promise(() => {}) as never);
    await user.click(within(await screen.findByRole("dialog")).getByRole("button", { name: "Publish" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("A newer data notice was published.");
    expect(field()).toHaveValue("My paste");
  });

  it("says the server's reason when the text is refused", async () => {
    versions();
    vi.spyOn(noticeApi, "impact").mockResolvedValue({ data: { current_version: 2, accounts_to_answer: 3 } } as never);
    vi.spyOn(noticeApi, "publish").mockRejectedValue({
      response: { status: 400, data: { text: ["The notice is longer than 100000 characters."] } },
    });
    const { user } = await openPage();

    await user.type(field(), " more");
    await user.click(screen.getByRole("button", { name: "Publish version 3" }));
    await user.click(within(await screen.findByRole("dialog")).getByRole("button", { name: "Publish" }));

    expect(await screen.findByText("The notice is longer than 100000 characters.")).toBeInTheDocument();
  });
});

describe("version history", () => {
  it("lists every version, newest first, and each reads in full", async () => {
    versions();
    const { user } = await openPage();

    const history = screen.getByRole("region", { name: "Version history" });
    const items = within(history).getAllByRole("listitem");
    expect(items.map((i) => i.textContent)).toEqual([
      expect.stringMatching(/^Version 2.*Nov 5, 2026.*Rita Dela Cruz/),
      expect.stringMatching(/^Version 1.*Nov 1, 2026/),
    ]);

    const read = within(items[1]).getByRole("button", { name: "Read version 1" });
    expect(read).toHaveAttribute("aria-expanded", "false");
    await user.click(read);
    expect(read).toHaveAttribute("aria-expanded", "true");
    expect(within(items[1]).getByText(/^Interim notice/).textContent).toBe(V1.text);
  });
});

describe("the System Admin", () => {
  it("reads every version but has no form to publish one (ADR-063 decision 9)", async () => {
    signInAs(ROLES.SYSTEM_ADMIN);
    versions();
    const impact = vi.spyOn(noticeApi, "impact");
    const { container } = await openPage();

    expect(screen.getByRole("group", { name: "Current version" })).toHaveTextContent("Version 2");
    expect(screen.queryByRole("textbox", { name: "Notice text" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /^Publish/ })).not.toBeInTheDocument();
    expect(screen.getByText("Only RDCO publishes a new version.")).toBeInTheDocument();
    expect(impact).not.toHaveBeenCalled();
    await expectNoBlockingA11yViolations(container);
  });
});

describe("when the history can't be read", () => {
  it("says so and offers to try again", async () => {
    const read = vi.spyOn(noticeApi, "versions").mockRejectedValueOnce({ response: { status: 500 } });
    read.mockResolvedValueOnce({ data: [V2, V1] } as never);
    const user = userEvent.setup();
    renderScreen(<NoticesPage />, { route: "/notices" });

    expect(await screen.findByRole("alert")).toHaveTextContent("The notices didn't load.");
    await user.click(screen.getByRole("button", { name: "Try again" }));
    expect(await screen.findByRole("heading", { level: 2, name: "Version history" })).toBeInTheDocument();
  });

  it("treats a response that isn't a list as a failed read (CODING_STANDARDS F1)", async () => {
    vi.spyOn(noticeApi, "versions").mockResolvedValue({ data: { count: 0, results: [] } } as never);
    renderScreen(<NoticesPage />, { route: "/notices" });

    expect(await screen.findByRole("alert")).toHaveTextContent("The notices didn't load.");
  });
});

/*
 * jsdom computes no layout, so a 360 px render is the same tree as any other
 * (see reflow360.test.tsx). What would push a control off a phone is a row
 * that can't wrap or a clamp on the words, so that is what is asserted.
 */
describe("at 360 px", () => {
  it("wraps every button row and clamps no text", async () => {
    versions();
    await openPage();

    for (const button of screen.getAllByRole("button")) {
      expect(button.parentElement!.className).toMatch(/\bflex-wrap\b/);
      expect(button.closest(".truncate, .whitespace-nowrap, [class*='line-clamp']")).toBeNull();
    }
    expect(field().className).toMatch(/\bw-full\b/);
  });
});
