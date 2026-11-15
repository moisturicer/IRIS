/**
 * The Documents rail (IR-1092 touch size).
 *
 * The browser check at 390 and 360 px with a touch pointer measured "Manage
 * documents" at 141 x 18 px, the one record-page control under 44 px. jsdom has
 * no layout, so this asserts the size class the link asks for.
 *
 * Every query goes through the accessible tree, by role and accessible name.
 */
import { describe, expect, it } from "vitest";

import { renderScreen, screen } from "@/test/render";

import { PaperDocuments } from "./PaperDocuments";

describe("Manage documents", () => {
  it("is a link to the Files section at least 44px tall on touch", () => {
    renderScreen(<PaperDocuments files={[]} manageHref="/records/7?section=review" />);

    const link = screen.getByRole("link", { name: "Manage documents" });
    expect(link).toHaveAttribute("href", "/records/7?section=review");
    expect(link).toHaveClass("min-h-11", "reading-split:min-h-9");
  });

  it("is not offered to a viewer who cannot manage the files", () => {
    renderScreen(<PaperDocuments files={[]} manageHref={null} />);

    expect(screen.queryByRole("link", { name: "Manage documents" })).not.toBeInTheDocument();
  });
});
