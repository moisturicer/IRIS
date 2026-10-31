import { describe, expect, it, vi } from "vitest";
import { renderScreen, screen, userEvent, within } from "@/test/render";
import { DpaConsentInline } from "./DpaConsentInline";
import { DpaConsentModal } from "./DpaConsentModal";

describe("disclosure processing notice (IR-123)", () => {
  it("explains external AI processing before the author consents", async () => {
    const user = userEvent.setup();
    renderScreen(<DpaConsentInline accepted={false} onAcceptedChange={vi.fn()} />);

    await user.click(screen.getByRole("button", { name: /view DPA terms/i }));

    expect(screen.getByText(/external AI providers outside CIT-U/i)).toBeVisible();
    expect(screen.getByText(/Voyage AI.*embedding.*reranking/i)).toBeVisible();
    expect(screen.getByText(/questions.*conversation context.*manuscript text/i)).toBeVisible();
    expect(screen.getByText(/pending.*DPO.*review/i)).toBeVisible();
    expect(screen.queryByText(/we do not.*share it outside CIT-U/i)).not.toBeInTheDocument();
    expect(screen.getByRole("checkbox", { name: /external AI processing/i })).not.toBeChecked();
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
