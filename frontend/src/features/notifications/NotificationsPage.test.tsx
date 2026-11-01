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
});
