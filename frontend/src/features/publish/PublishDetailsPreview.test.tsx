import { useState } from "react";
import { describe, expect, it, vi } from "vitest";

import { expectNoBlockingA11yViolations } from "@/test/axe";
import { render, screen, userEvent, waitFor } from "@/test/render";

import { PublishDetailsPreview } from "./PublishDetailsPreview";

vi.mock("@/features/records/paper-view/PaperPdfReader", () => ({
  PaperPdfReader: () => <p>Shared authenticated PDF reader</p>,
}));

function Details() {
  const [title, setTitle] = useState("Original title");

  return (
    <label>
      Title
      <input value={title} onChange={(event) => setTitle(event.target.value)} />
    </label>
  );
}

describe("PublishDetailsPreview (IR-834)", () => {
  it("moves focus between narrow-screen panes without losing Details edits", async () => {
    const user = userEvent.setup();
    render(
      <PublishDetailsPreview recordId={42} sourceKey={0}>
        <Details />
      </PublishDetailsPreview>,
    );

    const details = screen.getByRole("button", { name: "Details" });
    const preview = screen.getByRole("button", { name: "Preview" });
    const title = screen.getByRole("textbox", { name: "Title" });

    expect(details).toHaveAttribute("aria-pressed", "true");
    expect(preview).toHaveAttribute("aria-pressed", "false");

    await user.clear(title);
    await user.type(title, "Edited while reading");

    await user.click(preview);
    expect(preview).toHaveAttribute("aria-pressed", "true");
    const previewRegion = screen.getByRole("region", { name: "Manuscript preview" });
    await waitFor(() => expect(previewRegion).toHaveFocus());

    await user.click(details);
    expect(details).toHaveAttribute("aria-pressed", "true");
    await waitFor(() => expect(title).toHaveFocus());
    expect(title).toHaveValue("Edited while reading");
  });

  it("has no serious or critical accessibility violations", async () => {
    const { container } = render(
      <PublishDetailsPreview recordId={42} sourceKey={0}>
        <Details />
      </PublishDetailsPreview>,
    );

    await expectNoBlockingA11yViolations(container);
  });
});
