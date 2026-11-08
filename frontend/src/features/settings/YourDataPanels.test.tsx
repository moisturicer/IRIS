/**
 * Settings' "Download my data" and "Delete my account" (ADR-051 §8, §11 and
 * decision 13, IR-787), asserted through the Settings page a person opens.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { accountsApi, type MyDeletionRequest } from "@/api/accounts";
import { useAuthStore } from "@/store/auth.store";
import { expectNoBlockingA11yViolations } from "@/test/axe";
import { renderScreen, screen, userEvent, waitFor, within } from "@/test/render";
import SettingsPage from "./SettingsPage";

const PENDING: MyDeletionRequest = {
  id: 7, status: "pending", created_at: "2026-11-08T02:00:00Z", decided_at: null, reason: "",
  can_cancel: true, blockers: [],
};

function mine(request: MyDeletionRequest | null) {
  return vi.spyOn(accountsApi, "myDeletionRequest").mockResolvedValue({ data: { request } } as never);
}

async function openPrivacy() {
  const user = userEvent.setup();
  const view = renderScreen(<SettingsPage />, { route: "/settings" });
  await user.click(screen.getByRole("button", { name: "Data privacy & consent" }));
  return { user, ...view };
}

const deletePanel = () => screen.getByRole("region", { name: "Delete my account" });
const downloadPanel = () => screen.getByRole("region", { name: "Download my data" });

beforeEach(() => {
  useAuthStore.setState({
    user: {
      id: 1, email: "reader@cit.edu", first_name: "Rea", last_name: "Der", role_name: "Student",
      college_name: "", department_name: "", course_name: "", consent_given: true,
      date_joined: "2026-09-01T00:00:00Z",
    } as never,
    isAuthenticated: true,
    authReady: true,
  });
});

afterEach(() => vi.restoreAllMocks());

describe("Delete my account", () => {
  it("says what goes and what stays before anything is sent, and asks first", async () => {
    mine(null);
    const request = vi.spyOn(accountsApi, "requestMyDeletion");
    const { user, container } = await openPrivacy();

    const panel = await screen.findByRole("region", { name: "Delete my account" });
    await within(panel).findByRole("button", { name: "Delete my account" });
    const goes = within(panel).getByRole("heading", { name: "What goes" }).nextElementSibling!;
    const stays = within(panel).getByRole("heading", { name: "What stays" }).nextElementSibling!;
    expect(goes).toHaveTextContent(/profile and photo/);
    expect(goes).toHaveTextContent(/can't sign in again/);
    expect(stays).toHaveTextContent(/author on published papers/);
    expect(stays).toHaveTextContent(/Audit records, which keep your name and email/);

    await user.click(within(panel).getByRole("button", { name: "Delete my account" }));
    const confirm = within(panel).getByRole("group", { name: "Delete my account" });
    expect(confirm).toHaveTextContent(/can't be undone/);
    expect(request).not.toHaveBeenCalled();
    await expectNoBlockingA11yViolations(container);
  });

  it("sends the request, then shows it pending with nothing blocking it", async () => {
    mine(null);
    const request = vi.spyOn(accountsApi, "requestMyDeletion").mockResolvedValue({ data: { request: PENDING } } as never);
    const { user } = await openPrivacy();

    await user.click(await within(deletePanel()).findByRole("button", { name: "Delete my account" }));
    await user.click(within(deletePanel()).getByRole("button", { name: "Send the request" }));

    const sent = await within(deletePanel()).findByRole("group", { name: "Your deletion request" });
    expect(sent).toHaveTextContent("Request sent on Nov 8, 2026, waiting for the System Admin");
    expect(sent).toHaveTextContent("Nothing is waiting on you");
    expect(request).toHaveBeenCalledTimes(1);
  });

  it("lists what blocks a pending request in plain words", async () => {
    mine({
      ...PENDING,
      blockers: [{
        kind: "sole_owner_in_review", record: 3, title: "Mangrove survey",
        message: "“Mangrove survey” is in review and has no other owner. RDCO must withdraw it or add an owner.",
      }],
    });
    await openPrivacy();

    const sent = await within(deletePanel()).findByRole("group", { name: "Your deletion request" });
    expect(sent).toHaveTextContent("It can't be confirmed until this is cleared");
    expect(within(sent).getByRole("listitem")).toHaveTextContent(/Mangrove survey.*RDCO must withdraw it or add an owner/);
  });

  it("cancels a pending request, and then offers deletion again", async () => {
    mine(PENDING);
    const cancel = vi.spyOn(accountsApi, "cancelMyDeletion").mockResolvedValue({
      data: { request: { ...PENDING, status: "cancelled", can_cancel: false } },
    } as never);
    const { user } = await openPrivacy();

    await user.click(await within(deletePanel()).findByRole("button", { name: "Cancel my request" }));

    expect(await within(deletePanel()).findByRole("status")).toHaveTextContent("You cancelled your request.");
    expect(within(deletePanel()).getByRole("button", { name: "Delete my account" })).toBeVisible();
    expect(cancel).toHaveBeenCalledTimes(1);
  });

  it("shows a rejection's reason, and lets them ask again", async () => {
    mine({ ...PENDING, status: "declined", can_cancel: false, decided_at: "2026-11-09T02:00:00Z", reason: "You chair an open panel." });
    await openPrivacy();

    const last = await within(deletePanel()).findByRole("group", { name: "Your last deletion request" });
    expect(last).toHaveTextContent("Your last request was rejected on Nov 9, 2026");
    expect(last).toHaveTextContent("Reason: You chair an open panel.");
    expect(within(deletePanel()).getByRole("button", { name: "Delete my account" })).toBeVisible();
  });

  it("says the server's reason when sending is refused", async () => {
    mine(null);
    vi.spyOn(accountsApi, "requestMyDeletion").mockRejectedValue({
      response: { status: 409, data: { detail: "You already have a pending deletion request." } },
    });
    const { user } = await openPrivacy();

    await user.click(await within(deletePanel()).findByRole("button", { name: "Delete my account" }));
    await user.click(within(deletePanel()).getByRole("button", { name: "Send the request" }));

    expect(await within(deletePanel()).findByRole("alert")).toHaveTextContent("You already have a pending deletion request.");
  });

  it("says when the request couldn't be read, and tries again", async () => {
    const read = vi.spyOn(accountsApi, "myDeletionRequest").mockRejectedValueOnce(new Error("offline"));
    read.mockResolvedValueOnce({ data: { request: null } } as never);
    const { user } = await openPrivacy();

    expect(await within(deletePanel()).findByRole("alert")).toHaveTextContent("didn't load");
    await user.click(within(deletePanel()).getByRole("button", { name: "Try again" }));
    expect(await within(deletePanel()).findByRole("button", { name: "Delete my account" })).toBeVisible();
  });
});

describe("Download my data", () => {
  beforeEach(() => {
    mine(null);
    URL.createObjectURL = vi.fn(() => "blob:mine");
    URL.revokeObjectURL = vi.fn();
  });

  it("shows progress while the file is prepared, then saves it", async () => {
    let finish!: (v: unknown) => void;
    vi.spyOn(accountsApi, "downloadMyData").mockReturnValue(new Promise((r) => { finish = r; }) as never);
    const click = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {});
    const { user, container } = await openPrivacy();

    await user.click(within(downloadPanel()).getByRole("button", { name: "Download my data" }));
    expect(within(downloadPanel()).getByRole("status")).toHaveTextContent("Preparing your file…");

    finish({ data: new Blob(["{}"], { type: "application/json" }) });
    expect(await within(downloadPanel()).findByText(/Your file was saved as iris-my-data\.json/)).toBeVisible();
    expect(click).toHaveBeenCalledTimes(1);
    await expectNoBlockingA11yViolations(container);
  });

  it.each([
    [429, /downloaded your data several times recently/],
    [500, /wasn't downloaded/],
  ])("says so when the download fails (%s)", async (status, text) => {
    vi.spyOn(accountsApi, "downloadMyData").mockRejectedValue({ response: { status } });
    const { user } = await openPrivacy();

    await user.click(within(downloadPanel()).getByRole("button", { name: "Download my data" }));

    await waitFor(() => expect(within(downloadPanel()).getByRole("alert")).toHaveTextContent(text));
  });
});

/*
 * jsdom computes no layout, so a 360 px render is the same tree as any other
 * (see reflow360.test.tsx). What would push a control off a phone is a row
 * that can't wrap or a clamp on the words, so that is what is asserted.
 */
describe("at 360 px", () => {
  const unwrapped = (el: Element) => !!el.closest(".truncate, .whitespace-nowrap, [class*='line-clamp']");

  it("wraps every button row in both panels and clips none of their words", async () => {
    mine(null);
    const { user } = await openPrivacy();
    await user.click(await within(deletePanel()).findByRole("button", { name: "Delete my account" }));

    for (const panel of [downloadPanel(), deletePanel()]) {
      for (const button of within(panel).getAllByRole("button")) {
        expect(button.parentElement!.className).toMatch(/\bflex-wrap\b/);
        expect(unwrapped(button)).toBe(false);
      }
      for (const item of within(panel).queryAllByRole("listitem")) expect(unwrapped(item)).toBe(false);
    }
  });
});
