import { describe, expect, it, vi } from "vitest";
import { renderScreen, screen, userEvent, within } from "@/test/render";
import { DpaConsentModal } from "./DpaConsentModal";

describe("disclosure processing notice (IR-123)", () => {
  it("explains external AI processing in the DPA terms", () => {
    renderScreen(<DpaConsentModal open onClose={vi.fn()} />);
    const dialog = screen.getByRole("dialog");

    expect(within(dialog).getByText(/external AI providers outside CIT-U/i)).toBeVisible();
    expect(within(dialog).getByText(/Voyage AI.*embedding.*reranking/i)).toBeVisible();
    expect(within(dialog).getByText(/questions.*conversation context.*manuscript text/i)).toBeVisible();
    expect(within(dialog).getByText(/pending.*DPO.*review/i)).toBeVisible();
    expect(within(dialog).queryByText(/we do not.*share it outside CIT-U/i)).not.toBeInTheDocument();
  });

  it("copies every displayed notice paragraph, including external processing", async () => {
    const user = userEvent.setup();
    renderScreen(<DpaConsentModal open onClose={vi.fn()} />);
    const dialog = screen.getByRole("dialog");

    await user.click(within(dialog).getByRole("button", { name: /copy content/i }));

    const copied = await navigator.clipboard.readText();
    expect(copied).toMatch(/external AI providers outside CIT-U/i);
    expect(copied).not.toMatch(/we do not.*share it outside CIT-U/i);
    for (const section of dialog.querySelectorAll("section")) {
      expect(copied).toContain(within(section).getByRole("heading").textContent);
      for (const paragraph of section.querySelectorAll("p, li")) {
        expect(copied).toContain(paragraph.textContent);
      }
    }
  });
});
