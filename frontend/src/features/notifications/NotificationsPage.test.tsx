/**
 * Notifications when its list fails to load (IR-745): "No notifications yet"
 * after an error would be untrue. And the page's shape (IR-1137): All / Unread
 * segments, day groups, an Open button on each record's row.
 */
import { afterEach, describe, expect, it, vi } from "vitest";

import { renderScreen, screen, userEvent } from "@/test/render";

import { NotificationBell } from "@/components/layout/NotificationBell";
import { useNotificationsStore } from "@/store/notifications.store";

import NotificationsPage from "./NotificationsPage";

const list = vi.fn();
const markRead = vi.fn();
const markAllRead = vi.fn();

vi.mock("@/api/notifications", () => ({
  notificationsApi: {
    list: () => list(),
    markRead: (id: number) => markRead(id),
    markAllRead: () => markAllRead(),
  },
}));

afterEach(() => vi.clearAllMocks());

const at = (id: number, created_at: string, message: string, record: number | null = id) => ({
  id, notif_type: 1, notif_type_name: "Record Routed", message,
  record, record_title: "T", sender: null, sender_name: null,
  recipient: 1, broadcast_to_role: null, created_at, is_read: false,
  resolved_at: null, resolved_label: "", target: null,
});

describe("Notifications", () => {
  it("says a failed load failed, never that the inbox is empty, and tries again", async () => {
    list
      .mockRejectedValueOnce(new Error("Network Error"))
      .mockResolvedValueOnce({ data: { results: [] } });
    renderScreen(<NotificationsPage />);

    expect(await screen.findByRole("heading", { name: "Couldn't load your notifications" })).toBeInTheDocument();
    expect(screen.queryByText("No notifications yet.")).not.toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "Try again" }));
    expect(await screen.findByRole("heading", { name: "No notifications yet." })).toBeInTheDocument();
  });

  it("gives a record's notification an Open button, and opening it marks it read", async () => {
    markRead.mockResolvedValue({});
    list.mockResolvedValueOnce({
      data: {
        results: [
          {
            ...at(7, new Date().toISOString(), 'ITSO finished its review of "Tide Gauge": Cleared.'),
            notif_type_name: "Record Advanced", record: 42, record_title: "Tide Gauge",
          },
        ],
      },
    });
    renderScreen(<NotificationsPage />);

    const link = await screen.findByRole("link", { name: /Open: .*ITSO finished its review of "Tide Gauge"/ });
    expect(link).toHaveAttribute("href", "/records/42");
    expect(link).toHaveTextContent("Open");

    await userEvent.click(link);
    expect(markRead).toHaveBeenCalledWith(7);
  });

  it("opens a Call's notice where the server says, though it has no record (IR-765)", async () => {
    list.mockResolvedValueOnce({
      data: {
        results: [{
          ...at(8, new Date().toISOString(), 'RDCO did not confirm your call "ICCE 2027". Reason: Broken link.', null),
          notif_type_name: "Call Rejected", target: "/opportunities/mine",
        }],
      },
    });
    renderScreen(<NotificationsPage />);

    const link = await screen.findByRole("link", { name: /Open: RDCO did not confirm your call/ });
    expect(link).toHaveAttribute("href", "/opportunities/mine");
    expect(screen.queryByRole("button", { name: "Mark as read" })).toBeNull();
  });

  describe("the page (IR-1137)", () => {
    it("groups by day as Today, Yesterday, This week, then Earlier", async () => {
      const day = 24 * 3600 * 1000;
      const now = new Date();
      now.setHours(12, 0, 0, 0);
      list.mockResolvedValueOnce({
        data: {
          results: [
            at(1, now.toISOString(), "From today"),
            at(2, new Date(now.getTime() - day).toISOString(), "From yesterday"),
            at(4, new Date(now.getTime() - 3 * day).toISOString(), "From this week"),
            at(3, "2026-01-05T09:00:00", "From January"),
          ],
        },
      });
      renderScreen(<NotificationsPage />);

      await screen.findByText("From today");
      expect(screen.getAllByRole("heading", { level: 2 }).map((h) => h.textContent))
        .toEqual(["Today", "Yesterday", "This week", "Earlier"]);
    });

    it("keeps the Unread count in step after marking one and marking all", async () => {
      markRead.mockResolvedValue({});
      markAllRead.mockResolvedValue({});
      const now = new Date().toISOString();
      list.mockResolvedValueOnce({
        data: { results: [at(1, now, "First", null), at(2, now, "Second", null), at(3, now, "Third", null)] },
      });
      renderScreen(<NotificationsPage />);

      expect(await screen.findByRole("button", { name: "Unread 3" })).toBeInTheDocument();
      await userEvent.click(screen.getAllByRole("button", { name: "Mark as read" })[0]);
      expect(await screen.findByRole("button", { name: "Unread 2" })).toBeInTheDocument();

      await userEvent.click(screen.getByRole("button", { name: /Mark all as read/ }));
      expect(await screen.findByRole("button", { name: "Unread 0" })).toBeInTheDocument();
    });
  });

  describe("with the bell beside it (IR-1137)", () => {
    const seed = () => {
      const now = new Date().toISOString();
      const rows = [at(1, now, "First", null), at(2, now, "Second", null), at(3, now, "Third", null)];
      useNotificationsStore.setState({ items: rows, unreadCount: 3 });
      list.mockResolvedValueOnce({ data: { results: rows } });
    };

    it("agrees on the unread count after marking one and after marking all", async () => {
      markRead.mockResolvedValue({});
      markAllRead.mockResolvedValue({});
      seed();
      renderScreen(
        <>
          <NotificationBell />
          <NotificationsPage />
        </>,
      );

      expect(await screen.findByRole("button", { name: "Unread 3" })).toBeInTheDocument();
      expect(screen.getByRole("button", { name: "Notifications, 3 unread" })).toBeInTheDocument();

      await userEvent.click(screen.getAllByRole("button", { name: "Mark as read" })[0]);
      expect(await screen.findByRole("button", { name: "Unread 2" })).toBeInTheDocument();
      expect(screen.getByRole("button", { name: "Notifications, 2 unread" })).toBeInTheDocument();

      await userEvent.click(screen.getByRole("button", { name: /Mark all as read/ }));
      expect(await screen.findByRole("button", { name: "Unread 0" })).toBeInTheDocument();
      expect(screen.getByRole("button", { name: "Notifications" })).toBeInTheDocument();
    });

    it("says so when marking read fails, and leaves the row unread", async () => {
      markRead.mockRejectedValue(new Error("Network Error"));
      seed();
      renderScreen(<NotificationsPage />);

      await userEvent.click((await screen.findAllByRole("button", { name: "Mark as read" }))[0]);

      expect(await screen.findByRole("alert")).toHaveTextContent("Couldn't update your notifications");
      expect(screen.getByRole("button", { name: "Unread 3" })).toBeInTheDocument();
    });

    it("keeps Mark all as read on the page, disabled when nothing is unread", async () => {
      list.mockResolvedValueOnce({ data: { results: [{ ...at(1, new Date().toISOString(), "Done"), is_read: true }] } });
      renderScreen(<NotificationsPage />);

      expect(await screen.findByRole("button", { name: /Mark all as read/ })).toBeDisabled();
    });
  });

  describe("a notification whose task has ended (ADR-069)", () => {
    const open = {
      id: 1, notif_type: 1, notif_type_name: "Record Routed",
      message: 'RDCO Final sent "Tide Gauge" to ITSO. It waits in ITSO\'s pool until a reviewer claims it.',
      record: 42, record_title: "Tide Gauge", sender: null, sender_name: null,
      recipient: null, broadcast_to_role: 3,
      created_at: new Date().toISOString(), is_read: false,
      resolved_at: null, resolved_label: "", target: null,
    };
    const settled = {
      ...open, id: 2, notif_type_name: "New Version Submitted",
      message: 'The owner submitted v2 of "Kelp Survey". Review the new version.',
      record: 43, record_title: "Kelp Survey",
      resolved_at: new Date().toISOString(), resolved_label: "Reviewed by you on 20 Oct",
    };

    it("shows the server's settled line, and no call to act", async () => {
      list.mockResolvedValueOnce({ data: { results: [open, settled] } });
      renderScreen(<NotificationsPage />);

      // The open one still asks: unread, with a way to mark it read.
      expect(await screen.findByText(/It waits in ITSO's pool/)).toBeInTheDocument();
      expect(screen.getAllByText("Unread:")).toHaveLength(1);

      // The settled one says what happened, from the server's words alone,
      // in a pill beside its date; it is still openable.
      expect(screen.getByText("Reviewed by you on 20 Oct")).toBeInTheDocument();
      expect(screen.getAllByRole("link", { name: /^Open:/ })).toHaveLength(2);
    });

    it("is not counted as unread, nor shown under the Unread filter", async () => {
      list.mockResolvedValueOnce({ data: { results: [open, settled] } });
      renderScreen(<NotificationsPage />);

      await userEvent.click(await screen.findByRole("button", { name: "Unread 1" }));

      expect(screen.getByRole("link", { name: /Open: .*It waits in ITSO's pool/ })).toBeInTheDocument();
      expect(screen.queryByRole("link", { name: /Review the new version/ })).not.toBeInTheDocument();
    });

    it("says you're up to date when only settled notifications remain", async () => {
      list.mockResolvedValueOnce({ data: { results: [settled] } });
      renderScreen(<NotificationsPage />);

      await userEvent.click(await screen.findByRole("button", { name: "Unread 0" }));

      expect(screen.getByRole("heading", { name: "You're up to date" })).toBeInTheDocument();
    });
  });
});
