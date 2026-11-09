import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { TokenUsageMeter } from "./TokenUsageMeter";
import { conversationTotals } from "../runtime/messages";
import type { ReaderUsage } from "@/api/runtimeReader";

const usage: ReaderUsage = {
  calls: 2, total_tokens: 20_500, context_tokens: 18_000, capacity_tokens: 272_000,
  reserved_tokens: 8_000, compacts_at_tokens: 180_000,
};

describe("TokenUsageMeter", () => {
  it("shows one reading: the reported context against the model window", async () => {
    render(<TokenUsageMeter usage={{ ...usage, context_tokens: 9_600 }} />);
    await userEvent.click(screen.getByRole("button", { name: "Context window 4% used" }));
    const tip = screen.getByRole("tooltip");
    expect(tip).toHaveTextContent("Context window");
    expect(tip).toHaveTextContent("9.6K / 272K tokens");
    expect(tip).toHaveTextContent("Reserved for response");
    expect(tip).not.toHaveTextContent("180K");
    expect(tip).not.toHaveTextContent("total");
  });

  it("omits the reserve legend when no reserve is known", async () => {
    render(<TokenUsageMeter usage={{ ...usage, reserved_tokens: null }} />);
    await userEvent.click(screen.getByRole("button", { name: "Context window 7% used" }));
    expect(screen.getByRole("tooltip")).not.toHaveTextContent("Reserved");
  });
});

describe("conversationTotals", () => {
  it("sums every run's reported total, with the live run replacing its stored copy", () => {
    const run = (id: string, total: number) => ({ id, usage: { ...usage, total_tokens: total } });
    const conversation = { runs: [run("a", 10_000), run("b", 5_000)] } as never;
    const totals = conversationTotals(conversation, run("b", 7_000) as never);
    expect(totals.totalTokens).toBe(17_000);
    expect(totals.latest?.total_tokens).toBe(7_000);
  });
});
