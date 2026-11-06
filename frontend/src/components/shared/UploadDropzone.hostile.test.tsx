/**
 * A hostile file name in the upload zone (IR-917).
 *
 * The name is chosen by whoever made the file and reaches the page in three
 * places: the refusal text, the "Uploading <name>" line and its progress bar
 * label. React writes all three as text or attribute values; these tests keep
 * it that way if anyone moves to a string template.
 */
import { afterEach, describe, expect, it, vi } from "vitest";

import { expectInert } from "@/test/hostile";
import { fireEvent, renderScreen, screen } from "@/test/render";

import { UploadDropzone } from "./UploadDropzone";

declare global {
  interface Window {
    __pwned?: unknown;
  }
}

afterEach(() => {
  delete window.__pwned;
});

const HOSTILE_NAMES = [
  '<img src=x onerror="window.__pwned=1">.docx',
  "<script>window.__pwned=1</script>.docx",
  '"><svg onload=window.__pwned=1>.docx',
  "javascript:window.__pwned=1.docx",
  "&lt;b&gt;bold&lt;/b&gt;.docx",
];

describe("an upload's file name", () => {
  it.each(HOSTILE_NAMES)("is shown as text in a refusal: %s", (name) => {
    const { container } = renderScreen(
      <UploadDropzone label="Upload manuscript" onFiles={vi.fn()} accept=".pdf" validate />,
    );

    fireEvent.drop(screen.getByRole("button", { name: /^Upload manuscript/ }), {
      dataTransfer: { files: [new File(["PK"], name, { type: "application/octet-stream" })] },
    });

    expect(screen.getByRole("alert").textContent).toBe(`${name} is not an accepted file. Accepted: PDF.`);
    expectInert(container);
    expect(window.__pwned).toBeUndefined();
  });

  it.each(HOSTILE_NAMES)("is shown as text while uploading and when the upload failed: %s", (name) => {
    const uploading = renderScreen(
      <UploadDropzone label="Upload manuscript" onFiles={vi.fn()} upload={{ status: "uploading", fileName: name, progress: 40 }} />,
    );

    expect(uploading.container.textContent).toContain(`Uploading ${name}`);
    expectInert(uploading.container);
    uploading.unmount();

    const failed = renderScreen(
      <UploadDropzone
        label="Upload manuscript"
        onFiles={vi.fn()}
        upload={{ status: "failed", fileName: name, error: "<img src=x onerror=window.__pwned=1>", onRetry: vi.fn() }}
      />,
    );

    expectInert(failed.container);
    expect(window.__pwned).toBeUndefined();
  });
});
