/**
 * The one status row while an answer is prepared (IR-596): the server's
 * lifecycle label, truthful elapsed time, Stop, and a single polite live
 * region that does not announce the clock.
 */
import userEvent from "@testing-library/user-event";
import { act } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { expectNoBlockingA11yViolations } from "@/test/axe";
import { renderScreen, screen } from "@/test/render";
import type { StreamingState } from "../hooks/useAskStream";

import { StreamStatusRow, formatElapsed } from "./StreamStatusRow";

function state(overrides: Partial<StreamingState> = {}): StreamingState {
  return { activity: "waiting", label: "Waiting…", text: "", citations: [], ...overrides };
}

describe("the status row", () => {
  it.each([
    ["waiting", "Waiting…"],
    ["thinking", "Thinking…"],
    ["preparing", "Preparing your answer…"],
  ] as const)("shows %s as %s", (activity, label) => {
    renderScreen(<StreamStatusRow state={state({ activity, label })} />);

    expect(screen.getByRole("status")).toHaveTextContent(label);
  });

  it("is a single polite live region that survives a change of state", () => {
    const { container, rerender } = renderScreen(<StreamStatusRow state={state()} />);
    const live = container.querySelectorAll("[aria-live], [role=status], [role=log], [role=alert]");
    expect(live).toHaveLength(1);
    expect(live[0]).toHaveAttribute("aria-live", "polite");

    rerender(<StreamStatusRow state={state({ activity: "thinking", label: "Thinking…" })} />);

    expect(container.querySelector("[role=status]")).toBe(live[0]);
    expect(live[0].textContent).toBe("Thinking…");
  });

  it("offers Stop only for a followed queued run", async () => {
    const onStop = vi.fn();
    const { rerender } = renderScreen(<StreamStatusRow state={state()} onStop={onStop} />);
    expect(screen.queryByRole("button", { name: /stop/i })).toBeNull();

    rerender(<StreamStatusRow state={state({ runId: "run-1" })} onStop={onStop} />);
    await userEvent.click(screen.getByRole("button", { name: "Stop answering" }));
    expect(onStop).toHaveBeenCalledTimes(1);
  });

  it("shows no percentage and no tool or step narration", () => {
    const { container } = renderScreen(<StreamStatusRow state={state({ activity: "thinking", label: "Thinking…" })} />);

    expect(container.textContent).not.toMatch(/%|search_|step|tool/i);
  });

  it("has no serious or critical accessibility violations", async () => {
    const { container } = renderScreen(<StreamStatusRow state={state({ runId: "run-1" })} onStop={() => {}} />);

    await expectNoBlockingA11yViolations(container);
  });
});

describe("elapsed time", () => {
  beforeEach(() => { vi.useFakeTimers({ toFake: ["setInterval", "clearInterval", "Date"] }); });
  afterEach(() => { vi.useRealTimers(); });

  it("formats seconds and minutes", () => {
    expect(formatElapsed(12_400)).toBe("12s");
    expect(formatElapsed(65_000)).toBe("1m 05s");
  });

  it("counts from the real submission, outside the live region", () => {
    renderScreen(<StreamStatusRow state={state({ startedAt: Date.now() })} />);
    expect(screen.queryByText(/\d+s$/)).toBeNull();

    act(() => { vi.advanceTimersByTime(12_000); });

    expect(screen.getByText("12s")).toBeInTheDocument();
    expect(screen.getByRole("status")).toHaveTextContent(/^Waiting…$/);
  });

  it("shows no time for a run followed after a reopen, whose start is unknown", () => {
    renderScreen(<StreamStatusRow state={state({ runId: "run-1" })} />);

    act(() => { vi.advanceTimersByTime(30_000); });

    expect(screen.queryByText(/\d+s$/)).toBeNull();
  });
});
