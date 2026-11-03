import { useState } from "react";
import { describe, expect, it, vi } from "vitest";

import { expectNoBlockingA11yViolations } from "@/test/axe";
import { render, screen, userEvent, waitFor } from "@/test/render";

import { PublishDetailsPreview } from "./PublishDetailsPreview";

const readerInstances = vi.hoisted(() => ({ next: 0 }));

vi.mock("@/features/records/paper-view/PaperPdfReader", async () => {
  const React = await import("react");

  return {
    PaperPdfReader: ({ recordId }: { recordId: number }) => {
      const [instance] = React.useState(() => ++readerInstances.next);
      return (
        <div
          data-testid="shared-paper-reader"
          data-record-id={String(recordId)}
          data-instance={String(instance)}
        >
          Shared authenticated PDF reader
        </div>
      );
    },
  };
});

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

  it("remounts the shared reader when the accepted source changes", () => {
    const { rerender } = render(
      <PublishDetailsPreview recordId={42} sourceKey={1}>
        <Details />
      </PublishDetailsPreview>,
    );

    const first = screen.getByTestId("shared-paper-reader").getAttribute("data-instance");

    rerender(
      <PublishDetailsPreview recordId={42} sourceKey={2}>
        <Details />
      </PublishDetailsPreview>,
    );

    const second = screen.getByTestId("shared-paper-reader").getAttribute("data-instance");
    expect(second).not.toBe(first);
    expect(screen.getByTestId("shared-paper-reader")).toHaveAttribute("data-record-id", "42");
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
