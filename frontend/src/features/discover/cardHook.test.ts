import { describe, expect, it } from "vitest";
import { CARD_HOOK_MAX, cardHook } from "./discoverUtils";

describe("cardHook", () => {
  it("shows the generated hook when there is one", () => {
    expect(
      cardHook({ ai_hook: "Turns food waste into power.", abstract: "Other opening. More." }),
    ).toBe("Turns food waste into power.");
  });

  it.each([null, undefined, "", "   "])("falls back to the abstract's first sentence for %j", (hook) => {
    expect(cardHook({ ai_hook: hook, abstract: "This thesis studies X. It also does Y." })).toBe(
      "This thesis studies X.",
    );
  });

  it("cuts a long first sentence to the card limit with an ellipsis", () => {
    const long = `${"word ".repeat(60)}end.`;
    const hook = cardHook({ ai_hook: null, abstract: long });
    expect(hook.length).toBeLessThanOrEqual(CARD_HOOK_MAX);
    expect(hook.endsWith("…")).toBe(true);
  });

  it("is empty when there is neither a hook nor an abstract", () => {
    expect(cardHook({ ai_hook: null, abstract: "" })).toBe("");
  });
});
