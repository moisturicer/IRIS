/**
 * An empty conversation offers starter questions (IR-1090, spec §4.11): at least
 * three, each one sends itself, and none names the institution.
 */
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, expect, test, vi } from "vitest";

import { apiClient } from "@/api/client";
import { INSTITUTION } from "@/config/institution";
import { expectNoBlockingA11yViolations } from "@/test/axe";

import { RuntimeReader } from "./RuntimeReader";

afterEach(() => vi.restoreAllMocks());

const snapshot = { protocol: "runs-reader-1", id: "c", revision: 0, runs: [], turns: [] };

function startEmpty() {
  vi.spyOn(apiClient, "get").mockResolvedValue({ data: snapshot });
  return vi.spyOn(apiClient, "post").mockResolvedValue({ data: { protocol: "runs-reader-1", id: "r",
    conversation_id: "c", state: "queued", plan: null, context: null, capabilities: { manual_compaction: false } } });
}

test("an empty conversation offers at least three starter questions", async () => {
  startEmpty();
  const { container } = render(<MemoryRouter><RuntimeReader /></MemoryRouter>);

  const starters = screen.getByRole("group", { name: "Suggested questions" });
  const questions = within(starters).getAllByRole("button");
  expect(questions.length).toBeGreaterThanOrEqual(3);
  for (const question of questions) {
    expect(question.textContent).not.toContain(INSTITUTION.shortName);
  }
  await expectNoBlockingA11yViolations(container);
});

test("choosing a starter asks that question at once", async () => {
  const post = startEmpty();
  const user = userEvent.setup();
  render(<MemoryRouter><RuntimeReader /></MemoryRouter>);

  const starters = screen.getByRole("group", { name: "Suggested questions" });
  const first = within(starters).getAllByRole("button")[0];
  const asked = first.textContent ?? "";
  await user.click(first);

  await waitFor(() => expect(post).toHaveBeenCalledWith("/ai/runtime/runs",
    expect.objectContaining({ question: asked }), expect.anything()));
});

test("a paper's conversation offers questions about that paper", () => {
  startEmpty();
  render(<MemoryRouter><RuntimeReader recordId={42} /></MemoryRouter>);

  const starters = screen.getByRole("group", { name: "Suggested questions" });
  expect(within(starters).getAllByRole("button").length).toBeGreaterThanOrEqual(3);
  expect(within(starters).getAllByRole("button")[0].textContent).toMatch(/this paper/i);
});

test("a conversation that has begun offers no starters", async () => {
  vi.spyOn(apiClient, "get").mockResolvedValue({ data: { ...snapshot, runs: [{ protocol: "runs-reader-1", id: "r",
    conversation_id: "c", question: "Compare", state: "running", version: 1, depth: "ordinary", awaiting_reader: false,
    plan: null, context: null, capabilities: { manual_compaction: false } }] } });
  render(<MemoryRouter><RuntimeReader conversationId="c" /></MemoryRouter>);

  await screen.findByText("Thinking");
  expect(screen.queryByRole("group", { name: "Suggested questions" })).not.toBeInTheDocument();
});
