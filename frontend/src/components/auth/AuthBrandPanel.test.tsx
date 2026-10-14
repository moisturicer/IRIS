/**
 * The entry screens' brand panel says what IRIS is, plainly (IR-535).
 *
 * One variant per screen purpose -- sign in, register, verify email, await
 * approval. Each states what IRIS is and what that screen is for, and none
 * carries a quotation, an invented figure or a claim of prestige: the register
 * panel used to quote a design brief as a testimonial and call IRIS "a
 * prestigious archive".
 *
 * Queried through the accessible tree only (IR-210). The panel is
 * `hidden lg:flex`, but jsdom applies no stylesheet, so it is in the tree here;
 * that it is hidden below `lg` is a browser check, recorded on the PR.
 */
import { describe, expect, it } from "vitest";

import { expectNoBlockingA11yViolations } from "@/test/axe";
import { render, screen, within } from "@/test/render";

import { AuthBrandPanel, type AuthPanelVariant } from "./AuthBrandPanel";

const CASES: Array<{ variant: AuthPanelVariant; purpose: RegExp }> = [
  { variant: "login", purpose: /^Sign in to pick up your submissions/ },
  { variant: "signup", purpose: /^Register as a student or as faculty\. Once you verify your email, RDCO approves/ },
  { variant: "verify", purpose: /^This page confirms the email address .* RDCO then approves/ },
  { variant: "pending", purpose: /^Your account is registered\. It opens once RDCO approves it\.$/ },
  { variant: "declined", purpose: /^Your account is registered, but RDCO did not approve it\.$/ },
];

function renderPanel(variant: AuthPanelVariant) {
  const { container } = render(<AuthBrandPanel variant={variant} />);
  return { container, panel: screen.getByRole("complementary", { name: "About IRIS" }) };
}

/** The panel's text as it is read out: decoration (the shelf) is aria-hidden. */
function readText(panel: HTMLElement): string {
  const read = panel.cloneNode(true) as HTMLElement;
  read.querySelectorAll("[aria-hidden='true']").forEach((node) => node.remove());
  return read.textContent ?? "";
}

describe.each(CASES)("the $variant brand panel", ({ variant, purpose }) => {
  it("says what IRIS is", () => {
    const { panel } = renderPanel(variant);
    const text = readText(panel);

    expect(text).toMatch(/IRIS is the university's research and IP disclosure system\./);
    expect(text).toMatch(/reviewed by an adviser and the university's offices/);
    // Proposals are accepted, not published: only theses and projects reach Discover.
    expect(text).toMatch(/theses and projects that clear review are published to Discover/);
  });

  it("says what this screen is for", () => {
    const { panel } = renderPanel(variant);

    expect(within(panel).getByText(purpose)).toBeInTheDocument();
  });

  it("names a different purpose from every other screen", () => {
    const { panel } = renderPanel(variant);
    const others = CASES.filter((c) => c.variant !== variant);

    others.forEach(({ purpose: other }) => expect(within(panel).queryByText(other)).toBeNull());
  });

  it("makes no quotation, figure or claim of prestige", () => {
    const { panel } = renderPanel(variant);
    // The copyright year is the one number the panel may carry.
    const text = readText(panel).replace(/© \d{4}/, "");

    expect(text).not.toMatch(/[“”"]/);
    expect(text).not.toMatch(/prestig|high-end|leading|premier|world-class/i);
    expect(text).not.toMatch(/\d/);
  });

  it("keeps the shelf out of what a screen reader reads", () => {
    const { panel } = renderPanel(variant);

    // The spine titles are decoration; read aloud they would be noise.
    expect(readText(panel)).not.toMatch(/\b(?:Thesis|Research|Project|Proposal)\b/);
  });

  it("has no serious or critical accessibility violation", async () => {
    const { container } = renderPanel(variant);
    await expectNoBlockingA11yViolations(container);
  });
});
