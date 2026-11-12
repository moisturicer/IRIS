/**
 * Sending the revised manuscript from the *Revision requested* card (IR-273).
 * Every query goes through the accessible tree; failures are toasts, so the
 * card never grows a message line.
 */
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { useUIStore } from "@/store/ui.store";
import { renderScreen, screen, waitFor } from "@/test/render";

import { RevisionManuscriptUpload } from "./RevisionManuscriptUpload";

const uploadManuscript = vi.fn();

vi.mock("@/api/records", () => ({
  recordsApi: {
    uploadManuscript: (id: number, file: File, options: unknown) => uploadManuscript(id, file, options),
  },
}));

const pdf = (name = "revised.pdf") => new File(["%PDF-1.7"], name, { type: "application/pdf" });

function open(staged = false) {
  const onUploaded = vi.fn();
  renderScreen(<RevisionManuscriptUpload recordId={7} staged={staged} onUploaded={onUploaded} />);
  return { onUploaded };
}

beforeEach(() => {
  useUIStore.setState({ toasts: [] });
  uploadManuscript.mockReset().mockResolvedValue({ data: {} });
});

describe("RevisionManuscriptUpload", () => {
  it("uploads the file, says so in a toast, and tells the page to re-read the record", async () => {
    const { onUploaded } = open();

    await userEvent.upload(screen.getByLabelText("Upload revised manuscript"), pdf());

    await waitFor(() => expect(onUploaded).toHaveBeenCalled());
    expect(uploadManuscript).toHaveBeenCalledWith(7, expect.objectContaining({ name: "revised.pdf" }), expect.anything());
    expect(useUIStore.getState().toasts[0]).toMatchObject({ type: "success" });
  });

  it("offers Replace and says the staged file is not submitted yet", () => {
    open(true);

    expect(screen.getByLabelText("Replace revised manuscript")).toBeInTheDocument();
    expect(screen.getByText("Revised manuscript ready, not yet submitted")).toBeInTheDocument();
  });

  it("reports a refusal as a toast and leaves the page alone", async () => {
    uploadManuscript.mockRejectedValue({ response: { data: { detail: "The manuscript is locked." } } });
    const { onUploaded } = open();

    await userEvent.upload(screen.getByLabelText("Upload revised manuscript"), pdf());

    await waitFor(() => expect(useUIStore.getState().toasts).toHaveLength(1));
    expect(useUIStore.getState().toasts[0]).toMatchObject({
      type: "error",
      persist: true,
      message: "The manuscript is locked.",
    });
    expect(onUploaded).not.toHaveBeenCalled();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    // Back to a button, so the owner can try again.
    expect(screen.getByLabelText("Upload revised manuscript")).toBeInTheDocument();
  });

  it("refuses a file that is not a PDF before sending anything", async () => {
    open();

    await userEvent.upload(
      screen.getByLabelText("Upload revised manuscript"),
      new File(["x"], "notes.docx", { type: "application/msword" }),
      { applyAccept: false },
    );

    expect(uploadManuscript).not.toHaveBeenCalled();
    expect(useUIStore.getState().toasts[0]).toMatchObject({ type: "error" });
  });
});
