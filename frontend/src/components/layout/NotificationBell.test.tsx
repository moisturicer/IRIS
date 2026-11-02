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
import { useNotificationsStore } from "@/store/notifications.store";
import type { Notification } from "@/types/notifications";

import { useUnreadNotificationsFetch } from "@/hooks/useNotifications";

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

/**
 * Node's `process`, where an unhandled rejection is reported. Vitest runs
 * these tests in Node, but `tsconfig.json` loads no Node types (the app ships
 * to a browser), so only the two methods this file needs are declared.
 */
type RejectionListener = (reason: unknown) => void;
const nodeProcess = (
  globalThis as unknown as {
    process: {
      on: (event: "unhandledRejection", listener: RejectionListener) => void;
      off: (event: "unhandledRejection", listener: RejectionListener) => void;
    };
  }
).process;

function signIn(id: number) {
  act(() => useAuthStore.getState().login(makeUser({ id }), validToken({ user_id: id }), "refresh"));
}

/**
 * What `AppShell` does: own the one unread fetch (IR-370). A bell on its own
 * fetches nothing, so the tests below mount the owner beside it.
 */
function FetchOwner() {
  useUnreadNotificationsFetch();
  return null;
}

/** The fetch owner and `count` bells, as a page with several bells has. */
function renderBell(count = 1) {
  return render(
    <MemoryRouter>
      <FetchOwner />
      {Array.from({ length: count }, (_, i) => (
        <NotificationBell key={i} />
      ))}
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


describe("the bell's visible count and accessible name (IR-777)", () => {
  it.each([
    [0, null, "Notifications"],
    [7, "7", "Notifications, 7 unread"],
    [20, "9+", "Notifications, 9+ unread"],
  ] as const)(
    "keeps the visible badge text in the accessible name at %i unread",
    (unreadCount, visibleBadge, accessibleName) => {
      useNotificationsStore.setState({ items: [], unreadCount });
      render(
        <MemoryRouter>
          <NotificationBell />
        </MemoryRouter>,
      );

      const bell = screen.getByRole("button", { name: accessibleName });
      if (visibleBadge === null) {
        expect(within(bell).queryByText(/\d/)).not.toBeInTheDocument();
      } else {
        expect(within(bell).getByText(visibleBadge)).toBeInTheDocument();
      }
    },
  );
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
    nodeProcess.on("unhandledRejection", unhandled);
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
      nodeProcess.off("unhandledRejection", unhandled);
    }
  });
});

describe("several bells sharing one fetch (IR-370)", () => {
  afterEach(() => vi.mocked(notificationsApi.list).mockReset());

  it("fetches nothing when a bell mounts without the owner", () => {
    signIn(1);
    render(
      <MemoryRouter>
        <NotificationBell />
      </MemoryRouter>,
    );
    expect(notificationsApi.list).not.toHaveBeenCalled();
  });

  it("shows every bell the same count, and moves them all when one is read", async () => {
    vi.mocked(notificationsApi.list).mockResolvedValueOnce(
      page([notification(1, "Your manuscript was returned", 41), notification(2, "A broadcast")]),
    );
    vi.mocked(notificationsApi.markRead).mockResolvedValue({} as never);
    vi.mocked(notificationsApi.markAllRead).mockResolvedValue({} as never);
    signIn(1);
    renderBell(3);

    expect(await screen.findAllByRole("button", { name: "Notifications, 2 unread" })).toHaveLength(3);
    expect(notificationsApi.list).toHaveBeenCalledTimes(1);

    const [first] = screen.getAllByRole("button", { name: "Notifications, 2 unread" });
    await userEvent.click(first);
    await userEvent.click(within(screen.getByRole("dialog")).getByRole("button", { name: /A broadcast/ }));
    expect(screen.getAllByRole("button", { name: "Notifications, 1 unread" })).toHaveLength(3);

    await userEvent.click(screen.getAllByRole("button", { name: "Notifications, 1 unread" })[1]);
    await userEvent.click(within(screen.getByRole("dialog")).getByRole("button", { name: "Mark all read" }));
    expect(screen.getAllByRole("button", { name: "Notifications" })).toHaveLength(3);
    expect(notificationsApi.list).toHaveBeenCalledTimes(1);
  });

  it("fetches nothing while signed out, and once more for each new session", async () => {
    vi.mocked(notificationsApi.list)
      .mockResolvedValueOnce(page([notification(1, "Account A's manuscript was returned", 41)]))
      .mockResolvedValueOnce(page([notification(2, "Account B has a review due")]));
    renderBell(3);
    expect(notificationsApi.list).not.toHaveBeenCalled();

    signIn(1);
    expect(await screen.findAllByRole("button", { name: "Notifications, 1 unread" })).toHaveLength(3);
    expect(notificationsApi.list).toHaveBeenCalledTimes(1);

    // The bells stay mounted throughout, as the shell's would if it did.
    act(() => useAuthStore.getState().logout());
    expect(screen.getAllByRole("button", { name: "Notifications" })).toHaveLength(3);
    expect(notificationsApi.list).toHaveBeenCalledTimes(1);

    signIn(2);
    await screen.findAllByRole("button", { name: "Notifications, 1 unread" });
    expect(notificationsApi.list).toHaveBeenCalledTimes(2);
    const dialog = await openBellAt(0);
    expect(within(dialog).getByText("Account B has a review due")).toBeInTheDocument();
  });

  it("fetches again when another account signs in over the first without signing out", async () => {
    vi.mocked(notificationsApi.list)
      .mockResolvedValueOnce(page([notification(1, "Account A's manuscript was returned", 41)]))
      .mockResolvedValueOnce(page([]));
    signIn(1);
    renderBell(3);
    expect(await screen.findAllByRole("button", { name: "Notifications, 1 unread" })).toHaveLength(3);

    signIn(2);
    await act(async () => {});
    expect(notificationsApi.list).toHaveBeenCalledTimes(2);
    expect(screen.getAllByRole("button", { name: "Notifications" })).toHaveLength(3);
  });

  async function openBellAt(index: number) {
    await userEvent.click(screen.getAllByRole("button", { name: /^Notifications/ })[index]);
    return screen.getByRole("dialog", { name: "Notifications" });
  }
});
