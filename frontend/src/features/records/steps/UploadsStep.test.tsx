/**
 * The manuscript's upload states without colour (IR-360).
 *
 * "Uploaded" is near-black and "Error" is maroon, and maroon is also the
 * brand. So each state also has its own glyph (a check, or an exclamation),
 * and the word stays in the badge. A rejected file's reason sits under the
 * drop zone with the same glyph a field error uses.
 */
import { beforeEach, describe, expect, it, vi } from "vitest";

import { renderScreen, screen, userEvent } from "@/test/render";

import { UploadsStep } from "./UploadsStep";

vi.mock("@/api/records", () => ({
  recordsApi: { uploadManuscript: vi.fn() },
}));

vi.mock("@/api/documents", () => ({
  documentsApi: { slots: vi.fn(), upload: vi.fn() },
}));

const { recordsApi } = await import("@/api/records");
const { documentsApi } = await import("@/api/documents");

beforeEach(() => {
  vi.mocked(recordsApi.uploadManuscript).mockResolvedValue({ data: {} } as never);
  vi.mocked(documentsApi.slots).mockResolvedValue({ data: [] } as never);
});

function fileInput(container: HTMLElement) {
  return container.querySelector<HTMLInputElement>('input[type="file"]')!;
}

describe("UploadsStep — the manuscript's upload state", () => {
  it("marks an uploaded manuscript with a check as well as the word", async () => {
    const user = userEvent.setup();
    const { container } = renderScreen(<UploadsStep recordId={7} hideSlots />);

    await user.upload(fileInput(container), new File(["%PDF"], "thesis.pdf", { type: "application/pdf" }));

    const badge = await screen.findByText("Uploaded");
    expect(badge.querySelector("i.fa-check")).toHaveAttribute("aria-hidden");
  });

  it("marks a rejected file with a glyph, in the badge and beside the reason", async () => {
    const user = userEvent.setup({ applyAccept: false });
    const { container } = renderScreen(<UploadsStep hideSlots />);

    await user.upload(fileInput(container), new File(["x"], "notes.txt", { type: "text/plain" }));

    const badge = await screen.findByText("Error");
    expect(badge.querySelector("i.fa-circle-exclamation")).toHaveAttribute("aria-hidden");
    const reason = screen.getByText("Only PDF files are accepted.");
    expect(reason.querySelector("i.fa-circle-exclamation")).toHaveAttribute("aria-hidden");
  });
});
