/**
 * The app header's search box is left off Paper View (IR-356): the page is
 * a reading surface, and the box does nothing there. The bell stays.
 *
 * Every query goes through the accessible tree, by role and accessible name.
 */
import { describe, expect, it, vi } from "vitest";

import { renderScreen, screen } from "@/test/render";

import { Header } from "./Header";

// The bell loads the reader's notifications; its own tests cover that.
vi.mock("./NotificationBell", () => ({
  NotificationBell: () => <button type="button" aria-label="Notifications" />,
}));

describe("the app header", () => {
  it("offers search on other screens", () => {
    renderScreen(<Header />, { route: "/records/mine" });

    expect(screen.getByRole("searchbox", { name: /search records/i })).toBeInTheDocument();
  });

  it("leaves search off Paper View, and keeps the bell", () => {
    renderScreen(<Header />, { route: "/records/41" });

    expect(screen.queryByRole("searchbox", { name: /search records/i })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Notifications" })).toBeInTheDocument();
  });
});
