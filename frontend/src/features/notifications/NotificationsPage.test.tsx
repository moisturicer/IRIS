/**
 * Notifications when its list fails to load (IR-745): "No notifications yet"
 * after an error would be untrue.
 */
import { afterEach, describe, expect, it, vi } from "vitest";

import { renderScreen, screen, userEvent } from "@/test/render";

import NotificationsPage from "./NotificationsPage";

const list = vi.fn();
const markRead = vi.fn();

vi.mock("@/api/notifications", () => ({
  notificationsApi: {
    list: () => list(),
    markRead: (id: number) => markRead(id),
    markAllRead: vi.fn(),
  },
}));

afterEach(() => vi.clearAllMocks());

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

  it("makes the whole notification one link to its record, and opening it marks it read", async () => {
    markRead.mockResolvedValue({});
    list.mockResolvedValueOnce({
      data: {
        results: [
          {
            id: 7, notif_type: 1, notif_type_name: "Record Advanced",
            message: 'ITSO finished its review of "Tide Gauge": Cleared.',
            record: 42, record_title: "Tide Gauge", sender: null, sender_name: null,
            recipient: 1, broadcast_to_role: null,
            created_at: new Date().toISOString(), is_read: false,
            resolved_at: null, resolved_label: "",
          },
        ],
      },
    });
    renderScreen(<NotificationsPage />);

    const link = await screen.findByRole("link", { name: /ITSO finished its review of "Tide Gauge"/ });
    expect(link).toHaveAttribute("href", "/records/42");
    expect(screen.queryByRole("link", { name: "View record" })).not.toBeInTheDocument();

    await userEvent.click(link);
    expect(markRead).toHaveBeenCalledWith(7);
  });

  describe("a notification whose task has ended (ADR-069)", () => {
    const open = {
      id: 1, notif_type: 1, notif_type_name: "Record Routed",
      message: 'RDCO Final sent "Tide Gauge" to ITSO. It waits in ITSO\'s pool until a reviewer claims it.',
      record: 42, record_title: "Tide Gauge", sender: null, sender_name: null,
      recipient: null, broadcast_to_role: 3,
      created_at: new Date().toISOString(), is_read: false,
      resolved_at: null, resolved_label: "",
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
      const openLink = await screen.findByRole("link", { name: /It waits in ITSO's pool/ });
      expect(openLink).toHaveTextContent("Unread:");
      expect(screen.getAllByRole("button", { name: "Mark as read" })).toHaveLength(1);

      // The settled one says what happened, from the server's words alone.
      const settledLink = screen.getByRole("link", { name: /Review the new version/ });
      expect(settledLink).toHaveTextContent("Reviewed by you on 20 Oct");
      expect(settledLink).not.toHaveTextContent("Unread:");
    });

    it("is not counted as unread, nor shown under the Unread filter", async () => {
      list.mockResolvedValueOnce({ data: { results: [open, settled] } });
      renderScreen(<NotificationsPage />);

      await userEvent.click(await screen.findByRole("button", { name: "Unread (1)" }));

      expect(screen.getByRole("link", { name: /It waits in ITSO's pool/ })).toBeInTheDocument();
      expect(screen.queryByRole("link", { name: /Review the new version/ })).not.toBeInTheDocument();
    });

    it("says nothing is waiting when only settled notifications remain", async () => {
      list.mockResolvedValueOnce({ data: { results: [settled] } });
      renderScreen(<NotificationsPage />);

      await userEvent.click(await screen.findByRole("button", { name: "Unread" }));

      expect(screen.getByRole("heading", { name: "You're all caught up." })).toBeInTheDocument();
      expect(screen.getByText("Nothing is waiting on you.")).toBeInTheDocument();
    });

    it("labels each notification in plain words, not by its system name", async () => {
      list.mockResolvedValueOnce({ data: { results: [open] } });
      renderScreen(<NotificationsPage />);

      expect(await screen.findByText("Sent for review")).toBeInTheDocument();
      expect(screen.queryByText("Record Routed")).not.toBeInTheDocument();
    });
  });
});
