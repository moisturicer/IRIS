/**
 * Settings' "May AI use your papers?" (ADR-054 decisions 11 to 13, IR-793),
 * asserted through the Settings page a person opens.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { accountsApi } from "@/api/accounts";
import { noticeApi } from "@/api/notice";
import { useAuthStore } from "@/store/auth.store";
import { expectNoBlockingA11yViolations } from "@/test/axe";
import { renderScreen, screen, userEvent, within } from "@/test/render";
import SettingsPage from "./SettingsPage";

const NOTICE = { version: 5, text: "IRIS data notice", published_at: "2026-11-02T08:00:00Z" };

function answered(ai_consent: boolean | null, version = 5) {
  return vi.spyOn(noticeApi, "current").mockResolvedValue({
    data: { ...NOTICE, answer: { version, ai_consent, answered_at: "2026-11-03T02:00:00Z" }, answer_required: false },
  } as never);
}

function changes(ai_consent: boolean, papers_updated = 0) {
  return vi.spyOn(accountsApi, "changeAiAnswer").mockResolvedValue({
    data: { answer: { version: 5, ai_consent, answered_at: "2026-11-03T02:00:00Z" }, changed: true, papers_updated },
  } as never);
}

async function openPrivacy() {
  const user = userEvent.setup();
  const view = renderScreen(<SettingsPage />, { route: "/settings" });
  await user.click(screen.getByRole("button", { name: "Data privacy & consent" }));
  const panel = screen.getByRole("region", { name: "May AI use your papers?" });
  await within(panel).findByRole("group", { name: "Your answer" });
  return { user, panel, ...view };
}

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
  vi.spyOn(accountsApi, "myDeletionRequest").mockResolvedValue({ data: { request: null } } as never);
});

afterEach(() => vi.restoreAllMocks());

describe("the person's AI answer", () => {
  it("shows the current answer and the notice version it was given under", async () => {
    answered(true, 4);
    const { panel, container } = await openPrivacy();

    const mine = within(panel).getByRole("group", { name: "Your answer" });
    expect(mine).toHaveTextContent("Yes, AI may use your papers");
    expect(mine).toHaveTextContent("Given under notice version 4 on Nov 3, 2026.");
    expect(panel).toHaveTextContent("Each paper keeps the answer it started with, and there is no setting per paper.");
    await expectNoBlockingA11yViolations(container);
  });

  it("before changing to No, says it reaches only papers from now on, then sends it", async () => {
    answered(true);
    const change = changes(false);
    const { user, panel } = await openPrivacy();

    await user.click(within(panel).getByRole("button", { name: "Change to No" }));
    const confirm = within(panel).getByRole("group", { name: "Change your answer to No" });
    expect(confirm).toHaveTextContent("This only affects papers from now on.");
    expect(confirm).toHaveTextContent("Your earlier papers keep their Yes and stay in use by AI");
    expect(change).not.toHaveBeenCalled();

    await user.click(within(confirm).getByRole("button", { name: "Change to No" }));

    expect(await within(panel).findByRole("status")).toHaveTextContent("Your answer is now No. It applies to papers from now on.");
    expect(within(panel).getByRole("group", { name: "Your answer" })).toHaveTextContent("No, AI doesn't use your papers");
    expect(change).toHaveBeenCalledWith({ ai_consent: false });
  });

  it("changing to Yes offers both choices with neither preselected, and requires one", async () => {
    answered(false);
    const change = changes(true);
    const { user, panel, container } = await openPrivacy();

    await user.click(within(panel).getByRole("button", { name: "Change to Yes" }));
    const which = within(panel).getByRole("group", { name: /Which papers does your Yes cover/ });
    const all = within(which).getByRole("radio", { name: "All my papers" });
    const fromNow = within(which).getByRole("radio", { name: "Only papers from now on" });
    expect(all).not.toBeChecked();
    expect(fromNow).not.toBeChecked();
    expect(all).toHaveAccessibleDescription(/will be sent to AI companies.*can't be recalled/);
    await expectNoBlockingA11yViolations(container);

    const confirm = within(panel).getByRole("group", { name: "Change your answer to Yes" });
    await user.click(within(confirm).getByRole("button", { name: "Change to Yes" }));
    expect(which).toHaveAccessibleDescription("Choose which papers your Yes covers.");
    expect(change).not.toHaveBeenCalled();
  });

  it.each([
    ["All my papers", "all", 2, "Your answer is now Yes. 2 papers you're Contact person of now hold your Yes."],
    ["Only papers from now on", "from_now", 0, "Your answer is now Yes."],
  ] as const)("sends %s and says what changed", async (label, papers, updated, said) => {
    answered(false);
    const change = changes(true, updated);
    const { user, panel } = await openPrivacy();

    await user.click(within(panel).getByRole("button", { name: "Change to Yes" }));
    await user.click(within(panel).getByRole("radio", { name: label }));
    const confirm = within(panel).getByRole("group", { name: "Change your answer to Yes" });
    await user.click(within(confirm).getByRole("button", { name: "Change to Yes" }));

    expect(await within(panel).findByRole("status")).toHaveTextContent(said);
    expect(change).toHaveBeenCalledWith({ ai_consent: true, papers });
  });

  it("keeps the answer when they back out", async () => {
    answered(true);
    const change = changes(false);
    const { user, panel } = await openPrivacy();

    await user.click(within(panel).getByRole("button", { name: "Change to No" }));
    await user.click(within(panel).getByRole("button", { name: "Keep my answer" }));

    expect(within(panel).queryByRole("group", { name: "Change your answer to No" })).not.toBeInTheDocument();
    expect(within(panel).getByRole("group", { name: "Your answer" })).toHaveTextContent("Yes, AI may use your papers");
    expect(change).not.toHaveBeenCalled();
  });

  it("says the server's reason when the change is refused", async () => {
    answered(true);
    vi.spyOn(accountsApi, "changeAiAnswer").mockRejectedValue({
      response: { status: 403, data: { detail: "Answer the current data notice first." } },
    });
    const { user, panel } = await openPrivacy();

    await user.click(within(panel).getByRole("button", { name: "Change to No" }));
    await user.click(within(within(panel).getByRole("group", { name: "Change your answer to No" })).getByRole("button", { name: "Change to No" }));

    expect(await within(panel).findByRole("alert")).toHaveTextContent("Answer the current data notice first.");
  });
});

/*
 * jsdom computes no layout, so a 360 px render is the same tree as any other
 * (see reflow360.test.tsx). What would push a control off a phone is a row
 * that can't wrap or a clamp on the words, so that is what is asserted.
 */
describe("at 360 px", () => {
  it("wraps the panel's button rows and clips none of its words", async () => {
    answered(false);
    const { user, panel } = await openPrivacy();
    await user.click(within(panel).getByRole("button", { name: "Change to Yes" }));

    for (const button of within(panel).getAllByRole("button")) {
      expect(button.parentElement!.className).toMatch(/\bflex-wrap\b/);
      expect(button.closest(".truncate, .whitespace-nowrap, [class*='line-clamp']")).toBeNull();
    }
  });
});
