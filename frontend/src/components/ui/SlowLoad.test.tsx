/**
 * A loader that goes on too long says so (IR-1078, audit FB-02): a line of text
 * after 2 s, and Try again after 10 s where the screen can read again.
 */
import { act } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { renderScreen, screen } from "@/test/render";

import { Skeleton } from "./Skeleton";
import { Spinner } from "./Spinner";

beforeEach(() => vi.useFakeTimers());
afterEach(() => vi.useRealTimers());

const wait = (ms: number) => act(() => { vi.advanceTimersByTime(ms); });

describe.each([
  ["Skeleton", (onRetry?: () => void) => <Skeleton label="Loading users…" onRetry={onRetry} />],
  ["Spinner", (onRetry?: () => void) => <Spinner size="lg" label="Loading users…" onRetry={onRetry} />],
] as const)("%s", (_name, loader) => {
  it("says nothing extra at first", () => {
    renderScreen(loader(vi.fn()));
    wait(1_999);
    expect(screen.queryByText(/still working/i)).toBeNull();
    expect(screen.queryByRole("button", { name: "Try again" })).toBeNull();
  });

  it("says it is still working after 2 s, with no button yet", () => {
    renderScreen(loader(vi.fn()));
    wait(2_000);
    expect(screen.getByText(/still working/i)).toBeVisible();
    expect(screen.queryByRole("button", { name: "Try again" })).toBeNull();
  });

  it("offers Try again after 10 s, and it reads again and starts the wait over", async () => {
    const onRetry = vi.fn();
    renderScreen(loader(onRetry));
    wait(10_000);
    const button = screen.getByRole("button", { name: "Try again" });
    act(() => button.click());
    expect(onRetry).toHaveBeenCalledOnce();
    expect(screen.queryByRole("button", { name: "Try again" })).toBeNull();
    expect(screen.queryByText(/still working/i)).toBeNull();
    wait(2_000);
    expect(screen.getByText(/still working/i)).toBeVisible();
  });

  it("offers no button where the screen gave no way to read again", () => {
    renderScreen(loader());
    wait(60_000);
    expect(screen.getByText(/taking too long/i)).toBeVisible();
    expect(screen.queryByRole("button", { name: "Try again" })).toBeNull();
  });
});

describe("Spinner size sm", () => {
  it("sits beside a verb and adds no words of its own", () => {
    const { container } = renderScreen(<Spinner size="sm" />);
    wait(60_000);
    expect(container).not.toHaveTextContent(/\w/);
  });
});
