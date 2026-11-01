/**
 * Unread notifications belong to one signed-in session (IR-746).
 *
 * The bell reads a store shared across the whole tab. Before this, signing
 * out left that store full, so the next person to sign in on the same tab saw
 * the previous account's notification text and record links until their own
 * fetch replaced it -- or for good, if that fetch failed. A fetch started by
 * the previous session could also land after the switch and overwrite the
 * new account's list.
 *
 * Only the network is mocked: the auth store and the notifications store are
 * the real ones, because the defect lives in how the two meet. Every query
 * goes through the accessible tree, by role and accessible name.
 */
import { afterEach, describe, expect, it, vi } from "vitest";
import { act, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";

import { makeUser, validToken } from "@/test/authFixtures";
import { useAuthStore } from "@/store/auth.store";
import type { Notification } from "@/types/notifications";

import { NotificationBell } from "./NotificationBell";

vi.mock("@/api/notifications", () => ({
  notificationsApi: { list: vi.fn(), markRead: vi.fn(), markAllRead: vi.fn() },
}));

const { notificationsApi } = await import("@/api/notifications");

function notification(id: number, message: string, record: number | null = null): Notification {
  return {
    id,
    notif_type: 1,
    notif_type_name: "review",
    message,
    record,
    record_title: record ? `Record ${record}` : null,
    sender: null,
    sender_name: null,
    recipient: null,
    broadcast_to_role: null,
    created_at: "2026-10-31T09:00:00Z",
    is_read: false,
  };
}

/** A list response, as the API client resolves it. */
function page(results: Notification[]) {
  return { data: { count: results.length, results } } as never;
}

/** A promise the test settles by hand, to land a response at a chosen moment. */
function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason: unknown) => void;
  const promise = new Promise<T>((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
}

function signIn(id: number) {
  act(() => useAuthStore.getState().login(makeUser({ id }), validToken({ user_id: id }), "refresh"));
}

function renderBell() {
  return render(
    <MemoryRouter>
      <NotificationBell />
    </MemoryRouter>,
  );
}

async function openBell() {
  await userEvent.click(screen.getByRole("button", { name: /^Notifications/ }));
  return screen.getByRole("dialog", { name: "Notifications" });
}

afterEach(() => {
  act(() => useAuthStore.getState().logout());
});

describe("NotificationBell across a change of account in one tab", () => {
  it("shows the next account none of the previous account's notifications", async () => {
    vi.mocked(notificationsApi.list).mockResolvedValueOnce(
      page([notification(1, "Account A's manuscript was returned", 41)]),
    );
    signIn(1);
    const first = renderBell();
    expect(await screen.findByRole("button", { name: "Notifications, 1 unread" })).toBeInTheDocument();

    // Signing out navigates away from the shell, so the bell unmounts.
    first.unmount();
    act(() => useAuthStore.getState().logout());

    // Account B's own fetch has not answered yet.
    vi.mocked(notificationsApi.list).mockReturnValueOnce(deferred<never>().promise);
    signIn(2);
    renderBell();

    const dialog = await openBell();
    expect(within(dialog).queryByText("Account A's manuscript was returned")).not.toBeInTheDocument();
    expect(within(dialog).queryByRole("link", { name: /Record 41/ })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Notifications" })).toBeInTheDocument();
  });

  it("shows nothing of the previous account when the next signs in over it without signing out", async () => {
    // `/login` has no guard, so a signed-in account can open it and sign in
    // as someone else: `login` runs with no `logout` before it.
    const accountALateFetch = deferred<never>();
    vi.mocked(notificationsApi.list)
      .mockResolvedValueOnce(page([notification(1, "Account A's manuscript was returned", 41)]))
      .mockReturnValueOnce(accountALateFetch.promise);
    signIn(1);
    const first = renderBell();
    expect(await screen.findByRole("button", { name: "Notifications, 1 unread" })).toBeInTheDocument();
    first.unmount();
    // A second surface of A's session asks again; it answers only later.
    const second = renderBell();
    second.unmount();

    vi.mocked(notificationsApi.list).mockRejectedValueOnce(new Error("Network Error"));
    signIn(2);
    renderBell();
    await act(async () => {
      accountALateFetch.resolve(page([notification(3, "Account A was assigned a reviewer", 42)]));
    });

    const dialog = await openBell();
    expect(within(dialog).queryByText("Account A's manuscript was returned")).not.toBeInTheDocument();
    expect(within(dialog).queryByText("Account A was assigned a reviewer")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Notifications" })).toBeInTheDocument();
  });

  it("empties the bell when the session is invalidated without a sign-out", async () => {
    vi.mocked(notificationsApi.list).mockResolvedValueOnce(
      page([notification(1, "Account A's manuscript was returned", 41)]),
    );
    signIn(1);
    renderBell();
    expect(await screen.findByRole("button", { name: "Notifications, 1 unread" })).toBeInTheDocument();

    // What a failed token refresh does: the tokens go, the page stays.
    act(() => useAuthStore.getState().clearTokens());

    expect(screen.getByRole("button", { name: "Notifications" })).toBeInTheDocument();
    const dialog = await openBell();
    expect(within(dialog).queryByText("Account A's manuscript was returned")).not.toBeInTheDocument();
  });

  it("discards the previous account's fetch when it answers after the switch", async () => {
    const accountAFetch = deferred<never>();
    vi.mocked(notificationsApi.list).mockReturnValueOnce(accountAFetch.promise);
    signIn(1);
    const first = renderBell();

    first.unmount();
    act(() => useAuthStore.getState().logout());

    vi.mocked(notificationsApi.list).mockResolvedValueOnce(
      page([notification(2, "Account B has a review due")]),
    );
    signIn(2);
    renderBell();
    expect(await screen.findByRole("button", { name: "Notifications, 1 unread" })).toBeInTheDocument();

    // Account A's request, sent before the sign-out, answers only now.
    await act(async () => {
      accountAFetch.resolve(
        page([
          notification(1, "Account A's manuscript was returned", 41),
          notification(3, "Account A was assigned a reviewer", 42),
        ]),
      );
    });

    const dialog = await openBell();
    expect(within(dialog).getByText("Account B has a review due")).toBeInTheDocument();
    expect(within(dialog).queryByText("Account A's manuscript was returned")).not.toBeInTheDocument();
    expect(within(dialog).queryByText("Account A was assigned a reviewer")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Notifications, 1 unread" })).toBeInTheDocument();
  });

  it("shows nothing of the previous account when the next account's fetch fails", async () => {
    const unhandled = vi.fn();
    process.on("unhandledRejection", unhandled);
    try {
      vi.mocked(notificationsApi.list).mockResolvedValueOnce(
        page([notification(1, "Account A's manuscript was returned", 41)]),
      );
      signIn(1);
      const first = renderBell();
      expect(await screen.findByRole("button", { name: "Notifications, 1 unread" })).toBeInTheDocument();

      first.unmount();
      act(() => useAuthStore.getState().logout());

      vi.mocked(notificationsApi.list).mockRejectedValueOnce(new Error("Network Error"));
      signIn(2);
      renderBell();

      const dialog = await openBell();
      expect(within(dialog).queryByText("Account A's manuscript was returned")).not.toBeInTheDocument();
      expect(screen.getByRole("button", { name: "Notifications" })).toBeInTheDocument();

      // Give a rejection that nothing handled time to surface.
      await new Promise((resolve) => setTimeout(resolve, 0));
      expect(unhandled).not.toHaveBeenCalled();
    } finally {
      process.off("unhandledRejection", unhandled);
    }
  });
});
