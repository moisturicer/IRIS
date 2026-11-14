/**
 * The danger variant (IR-359). Its colour is maroon like the primary button's,
 * so what makes a destructive action unmistakable is not the colour: it is the
 * verb on the label, which the caller writes, and the warning glyph, which the
 * variant adds on its own.
 */
import { describe, expect, it, vi } from "vitest";
import { Route, Routes } from "react-router-dom";
import defaultColors from "tailwindcss/colors";

import { renderScreen, screen, userEvent } from "@/test/render";

import { Button, ButtonLink } from "./Button";

describe("Button", () => {
  it("marks a danger action with a glyph, without changing its accessible name", () => {
    const { container } = renderScreen(<Button variant="danger">Decline</Button>);

    expect(screen.getByRole("button", { name: "Decline" })).toBeInTheDocument();
    expect(container.querySelector("i.fa-triangle-exclamation")).toHaveAttribute("aria-hidden");
  });

  it("adds no glyph to a primary action", () => {
    const { container } = renderScreen(<Button>Approve</Button>);

    expect(container.querySelector("i.fa-triangle-exclamation")).toBeNull();
  });

  it("shows the spinner in place of the glyph while a danger action is loading", () => {
    const { container } = renderScreen(<Button variant="danger" loading>Decline</Button>);

    expect(container.querySelector("i.fa-triangle-exclamation")).toBeNull();
    expect(container.querySelector("svg.animate-spin")).not.toBeNull();
  });
});

/**
 * One button component (IR-1088; audit VIS-04 and CMP-05, spec §4.10): every
 * action is a pill in sentence case, and a disabled one is legible and says why.
 */
const VARIANTS = ["primary", "secondary", "danger", "ghost", "outline"] as const;
const TEXT_SIZES = ["sm", "md", "lg", "page", "full"] as const;

/** WCAG relative luminance of a #rrggbb colour. */
function luminance(hex: string): number {
  const channels = [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16) / 255);
  const [r, g, b] = channels.map((c) => (c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4));
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}

function contrast(a: string, b: string): number {
  const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x);
  return (hi + 0.05) / (lo + 0.05);
}

describe("Button shape", () => {
  it.each(VARIANTS)("is a pill in the %s variant, with no uppercase tracking", (variant) => {
    renderScreen(<Button variant={variant}>Save</Button>);

    const button = screen.getByRole("button", { name: "Save" });
    expect(button).toHaveClass("rounded-full");
    expect(button).not.toHaveClass("rounded-lg");
    expect(button).not.toHaveClass("uppercase");
  });

  it.each(TEXT_SIZES)("keeps the pill at the %s size", (size) => {
    renderScreen(<Button size={size}>Save</Button>);

    expect(screen.getByRole("button", { name: "Save" })).toHaveClass("rounded-full");
  });

  it("makes the page size a 44px pill, the height of a page action", () => {
    renderScreen(<Button size="page">Continue</Button>);

    expect(screen.getByRole("button", { name: "Continue" })).toHaveClass("min-h-11", "px-5");
  });

  it("gives a link that looks like a button the same pill", () => {
    renderScreen(<ButtonLink to="/x" variant="outline">Open</ButtonLink>, { route: "/" });

    expect(screen.getByRole("link", { name: "Open" })).toHaveClass("rounded-full");
  });
});

describe("Button disabled state", () => {
  it.each([...VARIANTS])("is Desk Stone with Faint Ink in the %s variant, never faded", (variant) => {
    renderScreen(<Button variant={variant} disabled>Save</Button>);

    const button = screen.getByRole("button", { name: "Save" });
    expect(button).toBeDisabled();
    expect(button).toHaveClass("disabled:bg-stone-200", "disabled:text-stone-500");
    expect(button.className).not.toMatch(/disabled:opacity-/);
  });

  it("is the same at the full size, which had a look of its own", () => {
    renderScreen(<Button size="full" disabled>Sign in</Button>);

    const button = screen.getByRole("button", { name: "Sign in" });
    expect(button).toHaveClass("disabled:bg-stone-200", "disabled:text-stone-500");
    expect(button.className).not.toMatch(/disabled:(bg|text)-stone-(100|700)/);
  });

  it("meets 3:1 between its label and its fill, read from the classes it actually carries", () => {
    renderScreen(<Button disabled>Save</Button>);

    // Desk Stone and Faint Ink are stone-200 and stone-500; the colours come
    // from the classes, so changing a class without changing the contrast fails.
    const shade = (property: "bg" | "text") => {
      const step = screen.getByRole("button", { name: "Save" }).className.match(new RegExp(`disabled:${property}-stone-([0-9]+)`))?.[1];
      return (defaultColors.stone as Record<string, string>)[step ?? ""];
    };
    expect(contrast(shade("text"), shade("bg"))).toBeGreaterThanOrEqual(3);
  });

  it("shows the reason beside a disabled button and ties it to the button", () => {
    renderScreen(<Button disabled disabledReason="Choose a file first.">Generate</Button>);

    const button = screen.getByRole("button", { name: "Generate" });
    const reason = screen.getByText("Choose a file first.");
    expect(reason).toBeVisible();
    expect(button).toHaveAccessibleDescription("Choose a file first.");
  });

  it("shows no reason once the button is enabled", () => {
    renderScreen(<Button disabledReason="Choose a file first.">Generate</Button>);

    expect(screen.queryByText("Choose a file first.")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Generate" })).not.toHaveAttribute("aria-describedby");
  });

  it("does not call a button that is busy disabled for a reason", () => {
    renderScreen(<Button loading disabledReason="Choose a file first.">Generate</Button>);

    expect(screen.queryByText("Choose a file first.")).not.toBeInTheDocument();
  });

  it("keeps a caller's own description alongside the reason", () => {
    renderScreen(
      <>
        <p id="note">Imports are checked first.</p>
        <Button disabled aria-describedby="note" disabledReason="Choose a file first.">Generate</Button>
      </>,
    );

    expect(screen.getByRole("button", { name: "Generate" }))
      .toHaveAccessibleDescription("Imports are checked first. Choose a file first.");
  });

  it("does not fire a click while disabled", async () => {
    const onClick = vi.fn();
    renderScreen(<Button disabled onClick={onClick}>Save</Button>);

    await userEvent.click(screen.getByRole("button", { name: "Save" }));

    expect(onClick).not.toHaveBeenCalled();
  });
});

/**
 * A navigation action is a link, not a button (IR-538, IR-213's decision), but
 * it looks like one. `ButtonLink` renders an anchor through the same variant
 * and size steps, so no caller copies the button's classes onto an `<a>`.
 */
describe("ButtonLink", () => {
  it("renders a link with the label as its accessible name, and reaches its destination", async () => {
    renderScreen(
      <Routes>
        <Route path="/" element={<ButtonLink to="/login">Sign in</ButtonLink>} />
        <Route path="/login" element={<p>Sign-in screen</p>} />
      </Routes>,
    );

    await userEvent.click(screen.getByRole("link", { name: "Sign in" }));

    expect(screen.getByText("Sign-in screen")).toBeInTheDocument();
  });

  it("takes the same variant and size steps as the button", () => {
    renderScreen(
      <>
        <Button variant="outline" size="full">Same</Button>
        <ButtonLink to="/x" variant="outline" size="full">Same</ButtonLink>
      </>,
    );

    const button = screen.getByRole("button", { name: "Same" });
    const link = screen.getByRole("link", { name: "Same" });
    expect(link).toHaveClass(...button.className.split(/\s+/).filter(Boolean));
  });
});
