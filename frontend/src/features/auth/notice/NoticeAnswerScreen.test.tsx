/**
 * The notice a signed-in person answers before anything else (ADR-054 decision
 * 3, IR-790), asserted through the route guard that shows it, so what is
 * checked is what a person reaching any page actually sees.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { Route, Routes } from "react-router-dom";
import { accountsApi } from "@/api/accounts";
import { authApi } from "@/api/auth";
import { noticeApi } from "@/api/notice";
import { ProtectedRoute } from "@/components/auth/ProtectedRoute";
import { ROLES } from "@/lib/constants";
import { useAuthStore } from "@/store/auth.store";
import { useNoticeStore } from "@/store/notice.store";
import { expectNoBlockingA11yViolations } from "@/test/axe";
import { makeUser, validToken } from "@/test/authFixtures";
import { renderScreen, screen, userEvent, waitFor, within } from "@/test/render";

const NOTICE = {
  version: 5,
  title: "IRIS data notice",
  subtitle: "Read before you continue",
  sections: [
    { title: "What IRIS keeps", body: "Your name.\nYour CIT-U email." },
    { title: "Who sees it", list: ["RDCO staff"] },
  ],
  published_at: "2026-11-02T08:00:00Z",
};

const agreement = () => screen.getByRole("checkbox", { name: /I have read the data notice/ });
const aiQuestion = () => screen.getByRole("group", { name: "May AI use your papers?" });
const save = () => screen.getByRole("button", { name: "Save my answer" });

function renderGuard() {
  return renderScreen(
    <Routes>
      <Route path="/login" element={<h1>Sign in</h1>} />
      <Route element={<ProtectedRoute allowedRoles={[ROLES.KTTO]} />}>
        <Route path="/review" element={<h1>Review queue</h1>} />
      </Route>
    </Routes>,
    { route: "/review" },
  );
}

beforeEach(() => {
  // A refresh while the notice is unanswered: the session is good, the account
  // could not load, and the notice is required.
  useAuthStore.setState({
    user: null,
    accessToken: validToken(),
    refreshToken: "refresh-1",
    isAuthenticated: true,
    authReady: true,
  });
  useNoticeStore.setState({ required: true });
  vi.spyOn(noticeApi, "current").mockResolvedValue({ data: { ...NOTICE, answer: null, answer_required: true } } as never);
});

afterEach(() => {
  vi.restoreAllMocks();
  useNoticeStore.setState({ required: false });
});

describe("the notice screen", () => {
  it("replaces the page, showing the server's notice with its version, date and text", async () => {
    const { container } = renderGuard();

    expect(await screen.findByRole("heading", { name: "IRIS data notice" })).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Review queue" })).not.toBeInTheDocument();
    const notice = screen.getByRole("region", { name: "Data notice" });
    expect(notice).toHaveTextContent("Version 5 · published Nov 2, 2026");
    expect(within(notice).getByText(/Your name\.\s+Your CIT-U email\./)).toBeInTheDocument();
    expect(within(notice).getByRole("listitem")).toHaveTextContent("RDCO staff");
    await expectNoBlockingA11yViolations(container);
  });

  it("preselects neither answer, and saving without them says what's missing and sends nothing", async () => {
    const user = userEvent.setup();
    const answer = vi.spyOn(noticeApi, "answer");
    renderGuard();
    await screen.findByRole("heading", { name: "IRIS data notice" });

    expect(agreement()).not.toBeChecked();
    for (const radio of within(aiQuestion()).getAllByRole("radio")) expect(radio).not.toBeChecked();
    await user.click(save());

    expect(agreement()).toHaveAccessibleDescription("Agree to the data-privacy agreement to continue.");
    expect(aiQuestion()).toHaveAccessibleDescription(/Choose Yes or No/);
    expect(answer).not.toHaveBeenCalled();
  });

  it("sends the version shown with both answers, loads the account, and then shows the page", async () => {
    const user = userEvent.setup();
    const answer = vi.spyOn(noticeApi, "answer").mockResolvedValue({ data: { answer_required: false } } as never);
    const me = vi.spyOn(authApi, "me").mockResolvedValue({ data: makeUser({ role_name: ROLES.KTTO }) } as never);
    renderGuard();
    await screen.findByRole("heading", { name: "IRIS data notice" });

    await user.click(agreement());
    await user.click(within(aiQuestion()).getByRole("radio", { name: "No" }));
    await user.click(save());

    expect(await screen.findByRole("heading", { name: "Review queue" })).toBeInTheDocument();
    expect(answer).toHaveBeenCalledWith({ notice_version: 5, agree_dpa: true, ai_consent: false });
    expect(me).toHaveBeenCalledTimes(1);
    expect(useNoticeStore.getState().required).toBe(false);
  });

  it("shows a newer notice published meanwhile, and asks for both answers again", async () => {
    const user = userEvent.setup();
    const newer = { ...NOTICE, version: 6, title: "IRIS data notice, revised" };
    const answer = vi.spyOn(noticeApi, "answer").mockRejectedValueOnce({
      response: { status: 409, data: { code: "notice_stale", notice: newer } },
    });
    renderGuard();
    await screen.findByRole("heading", { name: "IRIS data notice" });

    await user.click(agreement());
    await user.click(within(aiQuestion()).getByRole("radio", { name: "Yes" }));
    await user.click(save());

    expect(await screen.findByRole("heading", { name: "IRIS data notice, revised" })).toBeInTheDocument();
    expect(screen.getByRole("alert")).toHaveTextContent(/newer notice was published/);
    expect(agreement()).not.toBeChecked();
    expect(within(aiQuestion()).getByRole("radio", { name: "Yes" })).not.toBeChecked();
    expect(screen.queryByRole("heading", { name: "Review queue" })).not.toBeInTheDocument();
    expect(answer).toHaveBeenCalledWith({ notice_version: 5, agree_dpa: true, ai_consent: true });
  });

  it("keeps the person on the screen while the save fails, and says so", async () => {
    const user = userEvent.setup();
    vi.spyOn(noticeApi, "answer").mockRejectedValueOnce({ response: { status: 500, data: {} } });
    renderGuard();
    await screen.findByRole("heading", { name: "IRIS data notice" });

    await user.click(agreement());
    await user.click(within(aiQuestion()).getByRole("radio", { name: "No" }));
    await user.click(save());

    expect(await screen.findByRole("alert")).toHaveTextContent("Your answer wasn't saved");
    expect(screen.queryByRole("heading", { name: "Review queue" })).not.toBeInTheDocument();
  });

  it("offers Sign out, which ends the session", async () => {
    const user = userEvent.setup();
    const logout = vi.spyOn(authApi, "logout").mockResolvedValue({} as never);
    renderGuard();
    await screen.findByRole("heading", { name: "IRIS data notice" });

    await user.click(screen.getByRole("button", { name: "Sign out" }));

    expect(await screen.findByRole("heading", { name: "Sign in" })).toBeInTheDocument();
    expect(logout).toHaveBeenCalledWith("refresh-1");
    expect(useAuthStore.getState().accessToken).toBeNull();
    expect(useNoticeStore.getState().required).toBe(false);
  });

  it("offers Request account deletion, which asks first and then sends", async () => {
    const user = userEvent.setup();
    const request = vi.spyOn(accountsApi, "requestMyDeletion").mockResolvedValue({} as never);
    renderGuard();
    await screen.findByRole("heading", { name: "IRIS data notice" });

    await user.click(screen.getByRole("button", { name: "Request account deletion" }));
    const confirm = screen.getByRole("group", { name: "Request account deletion" });
    expect(confirm).toHaveTextContent(/once the System Admin confirms it/);
    expect(request).not.toHaveBeenCalled();

    await user.click(within(confirm).getByRole("button", { name: "Send the request" }));

    expect(await screen.findByRole("status")).toHaveTextContent("Your request was sent.");
    expect(request).toHaveBeenCalledTimes(1);
  });

  it("asks which papers when a previous No becomes a Yes, assuming neither, and sends the choice (IR-791)", async () => {
    const user = userEvent.setup();
    vi.spyOn(noticeApi, "current").mockResolvedValue({
      data: { ...NOTICE, answer: { version: 4, ai_consent: false, answered_at: "2026-10-01T00:00:00Z" }, answer_required: true },
    } as never);
    const answer = vi.spyOn(noticeApi, "answer").mockResolvedValue({ data: { answer_required: false } } as never);
    vi.spyOn(authApi, "me").mockResolvedValue({ data: makeUser({ role_name: ROLES.KTTO }) } as never);
    const { container } = renderGuard();
    await screen.findByRole("heading", { name: "IRIS data notice" });

    const papers = () => screen.queryByRole("group", { name: /Which papers does your Yes cover/ });
    await user.click(agreement());
    expect(papers()).not.toBeInTheDocument();
    await user.click(within(aiQuestion()).getByRole("radio", { name: "Yes" }));
    const group = papers()!;
    const all = within(group).getByRole("radio", { name: "All my papers" });
    expect(all).not.toBeChecked();
    expect(within(group).getByRole("radio", { name: "Only papers from now on" })).not.toBeChecked();
    expect(all).toHaveAccessibleDescription(/can't be recalled/);
    await expectNoBlockingA11yViolations(container);

    await user.click(save());
    expect(group).toHaveAccessibleDescription("Choose which papers your Yes covers.");
    expect(answer).not.toHaveBeenCalled();

    await user.click(all);
    await user.click(save());
    expect(await screen.findByRole("heading", { name: "Review queue" })).toBeInTheDocument();
    expect(answer).toHaveBeenCalledWith({ notice_version: 5, agree_dpa: true, ai_consent: true, papers: "all" });
  });

  it("asks nothing about papers when the previous answer was Yes or there was none", async () => {
    const user = userEvent.setup();
    for (const previous of [true, null]) {
      vi.spyOn(noticeApi, "current").mockResolvedValue({
        data: { ...NOTICE, answer: previous === null ? null : { version: 4, ai_consent: previous, answered_at: null }, answer_required: true },
      } as never);
      const { unmount } = renderGuard();
      await screen.findByRole("heading", { name: "IRIS data notice" });
      await user.click(within(aiQuestion()).getByRole("radio", { name: "Yes" }));
      expect(screen.queryByRole("group", { name: /Which papers does your Yes cover/ })).not.toBeInTheDocument();
      unmount();
    }
  });

  it("re-reads the notice when the tab comes back, and shows a newer one", async () => {
    const user = userEvent.setup();
    const current = vi.spyOn(noticeApi, "current");
    renderGuard();
    await screen.findByRole("heading", { name: "IRIS data notice" });
    await user.click(agreement());

    current.mockResolvedValue({ data: { ...NOTICE, version: 7, title: "IRIS data notice, July" } } as never);
    document.dispatchEvent(new Event("visibilitychange"));

    expect(await screen.findByRole("heading", { name: "IRIS data notice, July" })).toBeInTheDocument();
    await waitFor(() => expect(agreement()).not.toBeChecked());
  });
});
