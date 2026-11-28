import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { vi, expect, test, afterEach } from "vitest";
import { apiClient } from "@/api/client";
import { expectNoBlockingA11yViolations } from "@/test/axe";
import recorded from "@/test/fixtures/runtimeReader.recorded.json";
import { RuntimeReader } from "./RuntimeReader";

afterEach(() => vi.restoreAllMocks());

/**
 * The recorded run, as the runtime serves it while it is still working. The recording holds a
 * finished run (`activity: null`), so the live fields are laid over it in the shape the runtime
 * publishes them (`ai/runs/public.py`): a coarse activity with its latest step, and the plan.
 */
const working = {
  ...recorded.live, state: "running", turn_id: null, finished_at: null, depth: "ordinary",
  question: "How do these studies sample water?",
  activity: { phase: "working", label: "Searching papers", since: "2026-11-04T00:00:01+00:00",
    step: { kind: "read", label: "Read 2 papers", detail: ["Sampling a river", "Gauge networks"] } },
  plan: { revision: 2, steps: [
    { id: "find", title: "Find the sampling sections", status: "done" },
    { id: "compare", title: "Compare how each study samples water", status: "in_progress" },
    { id: "write", title: "Write the answer", status: "pending" },
    { id: "check", title: "Check the figures", status: "blocked" },
  ] },
};

function open(run: Record<string, unknown>) {
  vi.spyOn(apiClient, "get").mockImplementation(async (path) => ({ data: String(path).includes("conversations")
    ? { ...recorded.conversation, runs: [run], turns: [] } : run }));
  return render(<MemoryRouter><RuntimeReader conversationId={recorded.conversation.id} /></MemoryRouter>);
}

test("a working run shows what it reports under a polite heading, and nothing it did not report", async () => {
  const { container } = open(working);
  const progress = await screen.findByRole("region", { name: "Research progress" });
  expect(within(progress).getByRole("heading", { name: "Researching…" })).toBeInTheDocument();
  const live = progress.querySelector("[aria-live]");
  expect(live).toHaveAttribute("aria-live", "polite");
  expect(live).toContainElement(within(progress).getByRole("heading"));
  expect(progress.querySelector("[aria-live=assertive], [role=alert]")).toBeNull();
  // IR-1306: no step chip or titles; the verb names the tool, and a screen reader hears what the run reported.
  expect(within(progress).getByText("Searching papers. Read 2 papers")).toHaveClass("sr-only");
  expect(within(progress).queryByText("Sampling a river")).not.toBeInTheDocument();
  expect(within(progress).getByText(/^(Reading the pages|Reading closely)…$/)).toBeInTheDocument();

  const steps = within(within(progress).getByRole("list", { name: "Research plan" })).getAllByRole("listitem");
  expect(steps.map(step => step.textContent)).toEqual([
    "Find the sampling sections Done",
    "Compare how each study samples water In progress",
    "Write the answer Upcoming",
    "Check the figures Blocked",
  ]);
  expect(steps[1]).toHaveAttribute("aria-current", "step");
  await expectNoBlockingA11yViolations(container);
});

test("a deep run is headed Thorough research", async () => {
  open({ ...working, depth: "deep" });
  expect(await screen.findByRole("heading", { name: "Thorough research…" })).toBeInTheDocument();
});

test("a run that reports nothing yet shows only the heading", async () => {
  open({ ...working, activity: null, plan: null });
  const progress = await screen.findByRole("region", { name: "Research progress" });
  expect(within(progress).getByRole("heading", { name: "Researching…" })).toBeInTheDocument();
  expect(within(progress).queryByRole("list")).not.toBeInTheDocument();
  // The screen reader hears the steady heading; sighted readers see the turning verb (IR-1306).
  expect(progress).toHaveTextContent(/^Researching…(Reading your question|Planning where to look)…(\d+m \d{2}s|\d+(\.\d)?s)?$/);
});

test("Stop sends the stop call and puts the question back in the box to edit and resend", async () => {
  const stopped = { ...working, state: "cancelled", activity: null };
  open(working);
  const post = vi.spyOn(apiClient, "post").mockResolvedValue({ data: stopped });
  const user = userEvent.setup();
  await screen.findByRole("region", { name: "Research progress" });
  expect(screen.getByRole("textbox")).toHaveValue("");
  await user.click(screen.getByRole("button", { name: "Stop research" }));
  expect(post).toHaveBeenCalledWith(`/ai/runtime/runs/${working.id}/cancel`, expect.anything(), expect.anything());
  expect(await screen.findByText("Stopped before an answer was ready.")).toBeInTheDocument();
  expect(screen.queryByRole("region", { name: "Research progress" })).not.toBeInTheDocument();
  expect(screen.getByRole("textbox")).toHaveValue("How do these studies sample water?");
  expect(screen.getByRole("textbox")).toHaveFocus();
  expect(screen.getByRole("button", { name: "Send message" })).toBeEnabled();
});
