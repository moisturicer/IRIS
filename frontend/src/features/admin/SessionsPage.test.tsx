/**
 * IR-1078: the Sessions list names who failed and its failure state has a
 * working Try again.
 *
 * IR-1028: revoking asks through ConfirmDialog, never the browser's confirm()
 * or alert(), and reports success and failure in a toast.
 */
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { ActiveSession } from "@/api/accounts";
import { useUIStore } from "@/store/ui.store";
import { expectNoBlockingA11yViolations } from "@/test/axe";
import { renderScreen, screen, userEvent, waitFor, within } from "@/test/render";

import SessionsPage from "./SessionsPage";

const sessions = vi.fn();
const revokeSession = vi.fn();
vi.mock("@/api/accounts", () => ({
  accountsApi: {
    sessions: (...args: unknown[]) => sessions(...args),
    revokeSession: (...args: unknown[]) => revokeSession(...args),
  },
}));

function session(overrides: Partial<ActiveSession> = {}): ActiveSession {
  return {
    jti: "jti-1",
    user_id: 3,
    user_name: "Ana Reyes",
    user_email: "ana@cit.edu",
    created_at: "2026-11-01T08:00:00Z",
    expires_at: "2026-11-08T08:00:00Z",
    ...overrides,
  };
}

beforeEach(() => {
  sessions.mockReset();
  revokeSession.mockReset();
  useUIStore.setState({ toasts: [] });
});

describe("SessionsPage", () => {
  it("blames IRIS for a server failure, and Try again reads the list again", async () => {
    sessions
      .mockRejectedValueOnce(Object.assign(new Error("500"), { response: { status: 500 } }))
      .mockResolvedValueOnce({ data: [] });
    renderScreen(<SessionsPage />);

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("The sessions didn't load. IRIS took too long to answer. Try again.");
    expect(alert).not.toHaveTextContent(/check your connection/i);

    await userEvent.click(screen.getByRole("button", { name: "Try again" }));
    expect(await screen.findByText("No active sessions")).toBeVisible();
    expect(sessions).toHaveBeenCalledTimes(2);
  });
});

describe("SessionsPage revoke confirmation (IR-1028)", () => {
  const toasts = () => useUIStore.getState().toasts;

  async function openRevoke() {
    const trigger = await screen.findByRole("button", { name: "Revoke" });
    await userEvent.click(trigger);
    return { trigger, dialog: await screen.findByRole("dialog", { name: /Revoke/ }) };
  }

  it("asks in a dialog that names the person, never the browser's confirm", async () => {
    const nativeConfirm = vi.spyOn(window, "confirm");
    sessions.mockResolvedValue({ data: [session()] });
    renderScreen(<SessionsPage />);

    const { dialog } = await openRevoke();

    expect(dialog).toHaveTextContent("Ana Reyes");
    expect(dialog).toHaveTextContent(/logged out/i);
    await expectNoBlockingA11yViolations(dialog);
    expect(nativeConfirm).not.toHaveBeenCalled();
    expect(revokeSession).not.toHaveBeenCalled();
    nativeConfirm.mockRestore();
  });

  it("does nothing on Cancel, and returns focus to the button that opened it", async () => {
    sessions.mockResolvedValue({ data: [session()] });
    renderScreen(<SessionsPage />);

    const { trigger, dialog } = await openRevoke();
    await userEvent.click(within(dialog).getByRole("button", { name: "Cancel" }));

    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    expect(revokeSession).not.toHaveBeenCalled();
    expect(toasts()).toHaveLength(0);
    await waitFor(() => expect(trigger).toHaveFocus());
  });

  it("revokes once on confirm, drops the row and says so in a toast", async () => {
    sessions.mockResolvedValue({ data: [session(), session({ jti: "jti-2", user_name: "Ben Cruz" })] });
    revokeSession.mockResolvedValue({});
    renderScreen(<SessionsPage />);

    const trigger = (await screen.findAllByRole("button", { name: "Revoke" }))[0];
    await userEvent.click(trigger);
    const dialog = await screen.findByRole("dialog", { name: /Revoke/ });
    await userEvent.click(within(dialog).getByRole("button", { name: "Revoke session" }));

    await waitFor(() => expect(revokeSession).toHaveBeenCalledTimes(1));
    expect(revokeSession).toHaveBeenCalledWith("jti-1");
    await waitFor(() => expect(toasts()).toEqual([
      expect.objectContaining({ type: "success", message: expect.stringContaining("Ana Reyes") }),
    ]));
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    expect(screen.queryByText("Ana Reyes")).not.toBeInTheDocument();
    expect(screen.getByText("Ben Cruz")).toBeInTheDocument();
  });

  it("puts focus on Refresh after a revoke, since the row it came from is gone", async () => {
    sessions.mockResolvedValue({ data: [session()] });
    revokeSession.mockResolvedValue({});
    renderScreen(<SessionsPage />);

    const { dialog } = await openRevoke();
    await userEvent.click(within(dialog).getByRole("button", { name: "Revoke session" }));

    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    await waitFor(() => expect(screen.getByRole("button", { name: "Refresh" })).toHaveFocus());
  });

  it("disables the buttons and labels the confirm while the revoke is in flight", async () => {
    sessions.mockResolvedValue({ data: [session()] });
    let finish: () => void = () => undefined;
    revokeSession.mockReturnValue(new Promise<void>((resolve) => { finish = resolve; }));
    renderScreen(<SessionsPage />);

    const { dialog } = await openRevoke();
    await userEvent.click(within(dialog).getByRole("button", { name: "Revoke session" }));

    expect(await within(dialog).findByRole("button", { name: "Please wait…" })).toBeDisabled();
    expect(within(dialog).getByRole("button", { name: "Cancel" })).toBeDisabled();
    expect(revokeSession).toHaveBeenCalledTimes(1);
    finish();
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
  });

  it("shows the server's reason in an error toast, never alert(), and keeps the row", async () => {
    const nativeAlert = vi.spyOn(window, "alert");
    sessions.mockResolvedValue({ data: [session()] });
    revokeSession.mockRejectedValue({
      response: { status: 404, data: { detail: "That session has already ended." } },
    });
    renderScreen(<SessionsPage />);

    const { dialog } = await openRevoke();
    await userEvent.click(within(dialog).getByRole("button", { name: "Revoke session" }));

    await waitFor(() => expect(toasts()).toEqual([
      expect.objectContaining({ type: "error", message: "That session has already ended." }),
    ]));
    expect(nativeAlert).not.toHaveBeenCalled();
    expect(screen.getByText("Ana Reyes")).toBeInTheDocument();
    nativeAlert.mockRestore();
  });
});
