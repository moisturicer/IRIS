import { lazy, type ComponentType } from "react";
import { act, render, screen } from "@testing-library/react";
import { createMemoryRouter, RouterProvider } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import { RouteErrorScreen } from "@/features/errors/RouteErrorScreen";
import { reloadPage } from "@/lib/readFailure";

import { DeferredPage } from "./DeferredPage";

vi.mock("@/lib/readFailure", async (importActual) => ({
  ...(await importActual<typeof import("@/lib/readFailure")>()),
  reloadPage: vi.fn(),
}));

afterEach(() => {
  vi.restoreAllMocks();
});

describe("DeferredPage", () => {
  it("says it is still working after 2 s and offers Try again, which starts the page over, after 10 s (IR-1078)", () => {
    vi.useFakeTimers();
    try {
      const PendingPage = lazy(() => new Promise<{ default: ComponentType }>(() => undefined));
      render(<DeferredPage message="Opening the paper"><PendingPage /></DeferredPage>);

      act(() => { vi.advanceTimersByTime(2_000); });
      expect(screen.getByText("Still working…")).toBeVisible();
      expect(screen.queryByRole("button", { name: "Try again" })).toBeNull();

      act(() => { vi.advanceTimersByTime(8_000); });
      act(() => screen.getByRole("button", { name: "Try again" }).click());
      expect(reloadPage).toHaveBeenCalledOnce();
    } finally {
      vi.useRealTimers();
    }
  });

  it("says what is loading in the reader's words, announced once, while a route bundle is pending (US-09)", () => {
    const pendingImport = new Promise<{ default: ComponentType }>(() => undefined);
    const PendingPage = lazy(() => pendingImport);

    render(
      <DeferredPage message="Opening the paper">
        <PendingPage />
      </DeferredPage>,
    );

    expect(screen.getByRole("status", { name: "Opening the paper" })).toBeInTheDocument();
    expect(screen.getByText("Opening the paper…")).toHaveAttribute("aria-hidden", "true");
  });

  it("lets a failed route chunk reach the recoverable route error screen", async () => {
    vi.spyOn(console, "error").mockImplementation(() => undefined);
    const failedImport = Promise.reject(new Error("Loading chunk 42 failed")) as Promise<{
      default: ComponentType;
    }>;
    const BrokenPage = lazy(() => failedImport);
    const router = createMemoryRouter(
      [{
        path: "/",
        errorElement: <RouteErrorScreen />,
        element: (
          <DeferredPage message="Opening Ask IRIS">
            <BrokenPage />
          </DeferredPage>
        ),
      }],
      { initialEntries: ["/"] },
    );

    render(<RouterProvider router={router} />);

    expect(await screen.findByRole("heading", { name: "Something went wrong" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Try again" })).toBeInTheDocument();
  });
});
