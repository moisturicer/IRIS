/**
 * IR-1078: the Sessions list names who failed and its failure state has a
 * working Try again.
 */
import { beforeEach, describe, expect, it, vi } from "vitest";

import { renderScreen, screen, userEvent } from "@/test/render";

import SessionsPage from "./SessionsPage";

const sessions = vi.fn();
vi.mock("@/api/accounts", () => ({
  accountsApi: { sessions: (...args: unknown[]) => sessions(...args), revokeSession: vi.fn() },
}));

beforeEach(() => sessions.mockReset());

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
