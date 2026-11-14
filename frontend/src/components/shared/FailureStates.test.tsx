/**
 * What a failed read says and offers (IR-1078): who failed, and Try again.
 */
import { afterEach, describe, expect, it, vi } from "vitest";

import { RequestTimeoutError } from "@/api/requestPolicy";
import { renderScreen, screen, userEvent } from "@/test/render";

import { InterruptedState } from "./InterruptedState";
import { LoadFailedAlert } from "./LoadFailedAlert";
import { ReadFailedState } from "./ReadFailedState";

afterEach(() => vi.restoreAllMocks());

describe("LoadFailedAlert", () => {
  it("is an alert with the message and a Try again that reads again", async () => {
    const onRetry = vi.fn();
    renderScreen(<LoadFailedAlert message="The sessions didn't load." onRetry={onRetry} />);

    expect(screen.getByRole("alert")).toHaveTextContent("The sessions didn't load.");
    await userEvent.click(screen.getByRole("button", { name: "Try again" }));
    expect(onRetry).toHaveBeenCalledOnce();
  });
});

describe("InterruptedState", () => {
  it("blames IRIS for the wait and offers Retry, ADR-061's name for the reader's choice to read again", async () => {
    const onRetry = vi.fn();
    renderScreen(<InterruptedState what="console" onRetry={onRetry} />);

    expect(screen.getByRole("alert")).toHaveTextContent("The console did not finish loading. IRIS took too long to answer. Try again.");
    await userEvent.click(screen.getByRole("button", { name: "Retry" }));
    expect(onRetry).toHaveBeenCalledOnce();
  });
});

describe("ReadFailedState", () => {
  const props = { interrupted: false, what: "research list", title: "Could not load your research", onRetry: vi.fn() };

  it("says what was not changed, then who failed", () => {
    renderScreen(<ReadFailedState {...props} lead="Nothing was changed." error={{ response: { status: 503 } }} />);
    expect(screen.getByRole("alert")).toHaveTextContent("Nothing was changed. IRIS took too long to answer. Try again.");
  });

  it("tells an offline reader to check their connection", () => {
    vi.spyOn(navigator, "onLine", "get").mockReturnValue(false);
    renderScreen(<ReadFailedState {...props} error={new RequestTimeoutError(30_000)} />);
    expect(screen.getByRole("alert")).toHaveTextContent("Check your connection and try again.");
  });

  it("keeps a screen's own reassurance in place of the picked sentence", () => {
    renderScreen(<ReadFailedState {...props} message="Your saved papers are safe in your account." />);
    expect(screen.getByRole("alert")).toHaveTextContent("Your saved papers are safe in your account.");
  });

  it("offers Try again", async () => {
    const onRetry = vi.fn();
    renderScreen(<ReadFailedState {...props} onRetry={onRetry} />);
    await userEvent.click(screen.getByRole("button", { name: "Try again" }));
    expect(onRetry).toHaveBeenCalledOnce();
  });
});
