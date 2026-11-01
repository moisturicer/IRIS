/**
 * Notifications when its list fails to load (IR-745): "No notifications yet"
 * after an error would be untrue.
 */
import { afterEach, describe, expect, it, vi } from "vitest";

import { renderScreen, screen, userEvent } from "@/test/render";

import NotificationsPage from "./NotificationsPage";

const list = vi.fn();

vi.mock("@/api/notifications", () => ({
  notificationsApi: {
    list: () => list(),
    markRead: vi.fn(),
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
});
