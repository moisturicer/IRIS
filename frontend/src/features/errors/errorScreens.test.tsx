/**
 * Not found and Something went wrong (IR-745), through a data router shaped
 * like the real one: a stand-in shell whose children sit under one
 * `errorElement`, a catch-all, and a standalone fallback at the root.
 *
 * Queries go through the accessible tree, by role and accessible name.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { useState } from "react";
import { Link, Outlet, createMemoryRouter, RouterProvider, type RouteObject } from "react-router-dom";

import { expectNoBlockingA11yViolations } from "@/test/axe";
import { render, screen, userEvent } from "@/test/render";

import { NotFoundScreen } from "./NotFoundScreen";
import { RouteErrorScreen } from "./RouteErrorScreen";

/**
 * Throws while `failing` is set: a page that recovers once the cause is gone.
 * A flag, not a countdown, because React retries a failed render once.
 */
let failing = false;
function Flaky() {
  if (failing) throw new Error("Cannot read properties of undefined (reading 'title')");
  return <h1>Flaky page</h1>;
}

/** Stands in for the shell, with something held in memory to survive a crash. */
function Shell() {
  const [draft, setDraft] = useState("");
  return (
    <div>
      <nav aria-label="Sidebar"><Link to="/">Discover</Link></nav>
      <label>
        Draft
        <input value={draft} onChange={(e) => setDraft(e.target.value)} />
      </label>
      <main><Outlet /></main>
    </div>
  );
}

function BrokenShell(): never {
  throw new Error("shell failed");
}

function routes(shell: () => JSX.Element = Shell): RouteObject[] {
  const ShellElement = shell;
  return [{
    errorElement: <RouteErrorScreen standalone />,
    children: [{
      element: <ShellElement />,
      children: [{
        errorElement: <RouteErrorScreen />,
        children: [
          { index: true, element: <h1>Discover</h1> },
          { path: "flaky", element: <Flaky /> },
          { path: "*", element: <NotFoundScreen /> },
        ],
      }],
    }],
  }];
}

function renderAt(path: string | string[], shell?: () => JSX.Element) {
  const router = createMemoryRouter(routes(shell), {
    initialEntries: Array.isArray(path) ? path : [path],
    initialIndex: Array.isArray(path) ? path.length - 1 : 0,
  });
  return render(<RouterProvider router={router} />);
}

beforeEach(() => {
  failing = false;
  // React and the router both log a caught render error; the test expects it.
  vi.spyOn(console, "error").mockImplementation(() => {});
  vi.spyOn(console, "warn").mockImplementation(() => {});
});

afterEach(() => vi.restoreAllMocks());

describe("an address that matches nothing", () => {
  it("shows Not found inside the shell, without saying whether anything is there", async () => {
    const { container } = renderAt("/no-such-page");

    expect(await screen.findByRole("heading", { level: 1, name: "Page not found" })).toBeInTheDocument();
    expect(screen.getByText("This page doesn't exist, or it isn't available to you.")).toBeInTheDocument();
    expect(screen.getByText("Error 404")).toBeInTheDocument();
    expect(screen.getByRole("navigation", { name: "Sidebar" })).toBeInTheDocument();
    await expectNoBlockingA11yViolations(container);
  });

  it("offers Discover, and Go back only when there is an IRIS page to go back to", async () => {
    renderAt("/no-such-page");
    await screen.findByRole("heading", { name: "Page not found" });
    expect(screen.queryByRole("button", { name: "Go back" })).not.toBeInTheDocument();

    await userEvent.click(screen.getByRole("link", { name: "Go to Discover" }));
    expect(await screen.findByRole("heading", { level: 1, name: "Discover" })).toBeInTheDocument();
  });

  it("goes back to the page the reader came from", async () => {
    renderAt(["/", "/no-such-page"]);
    await screen.findByRole("heading", { name: "Page not found" });

    await userEvent.click(screen.getByRole("button", { name: "Go back" }));
    expect(await screen.findByRole("heading", { level: 1, name: "Discover" })).toBeInTheDocument();
  });

  it("names the subject when the page knows it", async () => {
    render(
      <RouterProvider router={createMemoryRouter([{ path: "/", element: <NotFoundScreen subject="Record" /> }])} />,
    );

    expect(await screen.findByRole("heading", { name: "Record not available" })).toBeInTheDocument();
    expect(screen.getByText("This record doesn't exist, or it isn't available to you.")).toBeInTheDocument();
  });
});

describe("a page that crashes", () => {
  it("is replaced inside the shell, announced, and keeps what the shell held", async () => {
    failing = true;
    const { container } = renderAt("/flaky");

    const alert = await screen.findByRole("alert");
    expect(screen.getByRole("heading", { level: 1, name: "Something went wrong" })).toBeInTheDocument();
    expect(alert).toBeInTheDocument();
    expect(screen.getByRole("navigation", { name: "Sidebar" })).toBeInTheDocument();
    await expectNoBlockingA11yViolations(container);

    await userEvent.type(screen.getByRole("textbox", { name: "Draft" }), "half a thought");
    failing = false;
    await userEvent.click(screen.getByRole("button", { name: "Try again" }));

    expect(await screen.findByRole("heading", { level: 1, name: "Flaky page" })).toBeInTheDocument();
    expect(screen.getByRole("textbox", { name: "Draft" })).toHaveValue("half a thought");
  });

  it("offers Reload page only once Try again has failed too", async () => {
    failing = true;
    renderAt("/flaky");

    await screen.findByRole("heading", { name: "Something went wrong" });
    expect(screen.queryByRole("button", { name: "Reload page" })).not.toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "Try again" }));

    expect(await screen.findByRole("button", { name: "Reload page" })).toBeInTheDocument();
    expect(screen.getByText(/This page failed again/)).toBeInTheDocument();
  });

  it("gives no reference number, and copies the details someone can send RDCO", async () => {
    failing = true;
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, "clipboard", { value: { writeText }, configurable: true });
    renderAt("/flaky?tab=2");

    await screen.findByRole("heading", { name: "Something went wrong" });
    expect(screen.queryByText(/reference/i)).not.toBeInTheDocument();

    await userEvent.click(screen.getByText("Details for RDCO"));
    await userEvent.click(screen.getByRole("button", { name: "Copy details" }));

    const copied = writeText.mock.calls[0][0] as string;
    expect(copied).toContain("Address: /flaky?tab=2");
    expect(copied).toContain("Error: Cannot read properties of undefined (reading 'title')");
    expect(copied).toMatch(/Time: \d{4}-\d{2}-\d{2}T/);
    expect(await screen.findByRole("status")).toHaveTextContent("Copied.");
  });

  it("falls back to a screen with no shell when the shell itself fails", async () => {
    renderAt("/", BrokenShell);

    expect(await screen.findByRole("heading", { level: 1, name: "Something went wrong" })).toBeInTheDocument();
    expect(screen.queryByRole("navigation", { name: "Sidebar" })).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Go to Discover" })).toHaveAttribute("href", "/");
  });
});
