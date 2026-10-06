/**
 * The upload zone (IR-405), which replaces `FileUploadZone`.
 *
 * The parent still owns the upload itself. This component owns what the author
 * meets before and around it:
 * - a refusal before anything is sent, naming the limit that was broken;
 * - progress a screen reader can hear;
 * - a failure that can be retried without choosing the file again.
 *
 * Checking is opt-in through `validate`. The two screens that used
 * `FileUploadZone` do not ask for it, so they keep exactly the behaviour they
 * had.
 */
import { describe, expect, it, vi } from "vitest";

import { expectNoBlockingA11yViolations } from "@/test/axe";
import { fireEvent, renderScreen, screen, userEvent } from "@/test/render";

import { UploadDropzone } from "./UploadDropzone";

const MB = 1024 * 1024;

function pdf(name = "thesis.pdf", bytes = 1024): File {
  const file = new File(["%PDF-1.4"], name, { type: "application/pdf" });
  Object.defineProperty(file, "size", { value: bytes });
  return file;
}

function docx(name = "thesis.docx"): File {
  return new File(["PK"], name, {
    type: "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
  });
}

function drop(zone: HTMLElement, files: File[]) {
  fireEvent.drop(zone, { dataTransfer: { files } });
}

describe("UploadDropzone", () => {
  it("is a named control that opens the file chooser from the keyboard", async () => {
    const click = vi.spyOn(HTMLInputElement.prototype, "click");
    const { container } = renderScreen(
      <UploadDropzone label="Upload manuscript" onFiles={vi.fn()} accept=".pdf" hint="PDF, up to 50 MB" />,
    );

    const zone = screen.getByRole("button", { name: "Upload manuscript" });
    zone.focus();
    await userEvent.keyboard("{Enter}");
    await userEvent.keyboard(" ");

    expect(click).toHaveBeenCalledTimes(2);
    expect(screen.getByText("PDF, up to 50 MB")).toBeInTheDocument();
    await expectNoBlockingA11yViolations(container);
  });

  it("hands a dropped file to its parent", () => {
    const onFiles = vi.fn();
    renderScreen(<UploadDropzone label="Upload manuscript" onFiles={onFiles} accept=".pdf" />);
    const file = pdf();

    drop(screen.getByRole("button", { name: "Upload manuscript" }), [file]);

    expect(onFiles).toHaveBeenCalledWith([file]);
  });

  it("refuses a file over the size limit before uploading, naming the limit", async () => {
    const onFiles = vi.fn();
    const { container } = renderScreen(
      <UploadDropzone label="Upload manuscript" onFiles={onFiles} accept=".pdf" validate maxBytes={50 * MB} />,
    );

    drop(screen.getByRole("button", { name: "Upload manuscript" }), [pdf("big.pdf", 62 * MB)]);

    expect(onFiles).not.toHaveBeenCalled();
    expect(screen.getByRole("alert")).toHaveTextContent("big.pdf is 62 MB. The limit is 50 MB.");
    await expectNoBlockingA11yViolations(container);
  });

  it("refuses a file of the wrong type before uploading, naming what is accepted", () => {
    const onFiles = vi.fn();
    renderScreen(
      <UploadDropzone label="Upload manuscript" onFiles={onFiles} accept=".pdf" validate maxBytes={50 * MB} />,
    );

    drop(screen.getByRole("button", { name: "Upload manuscript" }), [docx()]);

    expect(onFiles).not.toHaveBeenCalled();
    expect(screen.getByRole("alert")).toHaveTextContent("thesis.docx is not an accepted file. Accepted: PDF.");
  });

  it("clears its refusal once an acceptable file arrives", () => {
    const onFiles = vi.fn();
    renderScreen(
      <UploadDropzone label="Upload manuscript" onFiles={onFiles} accept=".pdf" validate maxBytes={50 * MB} />,
    );
    const zone = screen.getByRole("button", { name: "Upload manuscript" });

    drop(zone, [docx()]);
    drop(zone, [pdf()]);

    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    expect(onFiles).toHaveBeenCalledOnce();
  });

  it("checks the type alone when no size limit is given", () => {
    const onFiles = vi.fn();
    renderScreen(<UploadDropzone label="Upload manuscript" onFiles={onFiles} accept=".pdf" validate />);
    const zone = screen.getByRole("button", { name: "Upload manuscript" });

    drop(zone, [pdf("huge.pdf", 900 * MB)]);
    drop(zone, [docx()]);

    expect(onFiles).toHaveBeenCalledOnce();
    expect(screen.getByRole("alert")).toHaveTextContent("Accepted: PDF.");
  });

  it("builds its accepted-types line from what it checks", () => {
    renderScreen(
      <UploadDropzone label="Upload manuscript" onFiles={vi.fn()} accept=".pdf,.docx" validate maxBytes={50 * MB} />,
    );

    expect(screen.getByText("PDF, DOCX, up to 50 MB")).toBeInTheDocument();
  });

  it("checks nothing unless asked to, as FileUploadZone did", () => {
    const onFiles = vi.fn();
    renderScreen(<UploadDropzone label="Upload manuscript" onFiles={onFiles} accept=".pdf" />);
    const file = docx();

    drop(screen.getByRole("button", { name: "Upload manuscript" }), [file]);

    expect(onFiles).toHaveBeenCalledWith([file]);
  });

  it("reports progress to assistive technology while uploading", async () => {
    const onFiles = vi.fn();
    const { container } = renderScreen(
      <UploadDropzone
        label="Upload manuscript"
        onFiles={onFiles}
        upload={{ status: "uploading", fileName: "thesis.pdf", progress: 40 }}
      />,
    );

    const bar = screen.getByRole("progressbar", { name: "Uploading thesis.pdf" });
    expect(bar).toHaveAttribute("aria-valuenow", "40");
    expect(screen.getByRole("status")).toHaveTextContent("Uploading thesis.pdf");
    // A second file cannot be started over the one in flight.
    expect(screen.queryByRole("button", { name: "Upload manuscript" })).not.toBeInTheDocument();
    await expectNoBlockingA11yViolations(container);
  });

  it("shows a failed upload with a retry that needs no new file", async () => {
    const onRetry = vi.fn();
    const { container } = renderScreen(
      <UploadDropzone
        label="Upload manuscript"
        onFiles={vi.fn()}
        upload={{ status: "failed", fileName: "thesis.pdf", error: "The connection dropped.", onRetry }}
      />,
    );

    expect(screen.getByRole("alert")).toHaveTextContent("thesis.pdf could not be uploaded. The connection dropped.");
    await userEvent.click(screen.getByRole("button", { name: "Retry upload" }));

    expect(onRetry).toHaveBeenCalledOnce();
    await expectNoBlockingA11yViolations(container);
  });

  it("keeps keyboard focus through an upload, and says when it is done", () => {
    const zoneProps = { label: "Upload manuscript", onFiles: vi.fn() };
    const { rerender } = renderScreen(<UploadDropzone {...zoneProps} />);
    screen.getByRole("button", { name: "Upload manuscript" }).focus();

    rerender(<UploadDropzone {...zoneProps} upload={{ status: "uploading", fileName: "thesis.pdf", progress: 0 }} />);
    expect(screen.getByRole("group", { name: "Upload in progress" })).toHaveFocus();

    rerender(<UploadDropzone {...zoneProps} upload={null} />);
    expect(screen.getByRole("button", { name: "Upload manuscript" })).toHaveFocus();
    expect(screen.getByRole("status")).toHaveTextContent("thesis.pdf uploaded");
  });

  it("does nothing while disabled", () => {
    const onFiles = vi.fn();
    renderScreen(<UploadDropzone label="Upload manuscript" onFiles={onFiles} disabled />);
    const zone = screen.getByRole("button", { name: "Upload manuscript" });

    drop(zone, [pdf()]);

    expect(zone).toHaveAttribute("aria-disabled", "true");
    expect(onFiles).not.toHaveBeenCalled();
  });
});
