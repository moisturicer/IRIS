import { lazy, type ComponentType } from "react";
import { render, screen } from "@testing-library/react";
import { createMemoryRouter, RouterProvider } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import { RouteErrorScreen } from "@/features/errors/RouteErrorScreen";

import { DeferredPage } from "./DeferredPage";

afterEach(() => {
  vi.restoreAllMocks();
});

describe("DeferredPage", () => {
  it("announces an accessible loading state while a route bundle is pending", () => {
    const pendingImport = new Promise<{ default: ComponentType }>(() => undefined);
    const PendingPage = lazy(() => pendingImport);

    render(
      <DeferredPage name="Paper View">
        <PendingPage />
      </DeferredPage>,
    );

    expect(screen.getByRole("status", { name: "Loading Paper View" })).toBeInTheDocument();
    expect(screen.getByText("Loading Paper View…")).toHaveAttribute("aria-hidden", "true");
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
          <DeferredPage name="Ask IRIS">
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
