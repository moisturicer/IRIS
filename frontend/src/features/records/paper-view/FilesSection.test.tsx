/**
 * Paper View's Files section (IR-411; spec §4.6, §4.10). It replaces the
 * Documents page, and carries over that page's IR-346 tests.
 *
 * **One upload path.** Every upload goes through `UploadDropzone`. A
 * reviewer's request for a slot is answered by uploading into that slot the
 * ordinary way (ADR-022 §Amendment 1, IR-346), so the slot takes an upload
 * even while the record is in review; an "Other" item, which has no slot, takes
 * one of its own.
 *
 * **One vocabulary.** A requested document reads Requested → Uploaded ·
 * awaiting review → Accepted, or Replacement needed with the reviewer's reason.
 *
 * Which items an upload answers is the server's rule, pinned by the API tests
 * in `apps/documents/tests/test_document_requests.py`. The fake server below
 * answers the way that rule does. Every query goes through the accessible tree.
 */
import { beforeEach, describe, expect, it, vi } from "vitest";

import { expectNoBlockingA11yViolations } from "@/test/axe";
import { fireEvent, renderScreen, screen, waitFor, within } from "@/test/render";
import type { RecordFile, SlotWithUploads } from "@/types/documents";
import type { DocumentRequest, DocumentRequestItem, RecordDetail } from "@/types/records";

import { FilesSection } from "./FilesSection";

const RECORD_ID = 9;
const ETHICS = 3;
const PATENT = 4;

let requests: DocumentRequest[];
let slots: SlotWithUploads[];
let attachments: RecordFile[];
const upload = vi.fn();
const uploadForRequestItem = vi.fn();
const uploadRecordFile = vi.fn();
const deleteFile = vi.fn();

/** The server's answer to an owner's upload: every open missing item it answers. */
function answer(match: (item: DocumentRequestItem) => boolean) {
  requests = requests.map((r) => {
    if (r.state !== "open") return r;
    const items = r.items.map((i) =>
      i.state === "missing" && match(i)
        ? { ...i, state: "uploaded" as const, state_label: "Uploaded", upload: 500, rejection_reason: null }
        : i,
    );
    const done = items.every((i) => i.state !== "missing");
    return { ...r, items, state: done ? "fulfilled" : "open", state_label: done ? "Fulfilled" : "Open" };
  });
}

vi.mock("@/api/records", () => ({
  recordsApi: {
    documentRequests: () => Promise.resolve({ data: structuredClone(requests) }),
    documentRequestSlots: () => Promise.resolve({ data: [] }),
  },
}));
vi.mock("@/api/documents", () => ({
  documentsApi: {
    slotsForRecord: () => Promise.resolve({ data: structuredClone(slots) }),
    files: () => Promise.resolve({ data: structuredClone(attachments) }),
    upload: (recordId: number, slotId: number, file: File, options: unknown) =>
      upload(recordId, slotId, file, options),
    uploadForRequestItem: (recordId: number, itemId: number, file: File, options: unknown) =>
      uploadForRequestItem(recordId, itemId, file, options),
    uploadRecordFile: (recordId: number, file: File, options: unknown) => uploadRecordFile(recordId, file, options),
    deleteFile: (fileId: number) => deleteFile(fileId),
    downloadUpload: vi.fn(),
    downloadFile: vi.fn(),
    deleteUpload: vi.fn(),
  },
}));

function item(overrides: Partial<DocumentRequestItem> = {}): DocumentRequestItem {
  return {
    id: 11, slot: ETHICS, label: "Ethics Clearance", state: "missing", state_label: "Missing",
    upload: null, uploaded_at: null, rejection_reason: null, decided_at: null,
    ...overrides,
  };
}

function openRequest(items: DocumentRequestItem[]): DocumentRequest {
  return {
    id: 1, party: "ierc", label: "IERC", state: "open", state_label: "Open",
    message: "Please upload the ethics clearance.", requested_by: "Ivy Ethics",
    created_at: "2026-09-20T02:00:00Z", closed_at: null, can_manage: false,
    items,
  };
}

const record = {
  id: RECORD_ID,
  abstract_file: "/api/v1/records/9/manuscript/",
  can_request_document: [],
  current_holders: [],
} as unknown as RecordDetail;

function slot(id: number, name: string): SlotWithUploads {
  return { id, name, record_type: 1, is_required: false, uploads: [] };
}

beforeEach(() => {
  attachments = [];
  uploadRecordFile.mockReset().mockImplementation((_record: number, file: File) => {
    attachments = [...attachments, attachment(70, file.name)];
    return Promise.resolve({ data: attachments[attachments.length - 1] });
  });
  deleteFile.mockReset().mockImplementation((fileId: number) => {
    attachments = attachments.filter((f) => f.id !== fileId);
    return Promise.resolve({ data: null });
  });
  slots = [slot(ETHICS, "Ethics Clearance"), slot(PATENT, "Patent Draft")];
  requests = [openRequest([item(), item({ id: 12, slot: null, label: "Consent form" })])];
  upload.mockReset().mockImplementation((_record: number, slotId: number) => {
    answer((i) => i.slot === slotId);
    return Promise.resolve({ data: { upload: { id: 500 }, extraction: { id: 1, status: "queued" } } });
  });
  uploadForRequestItem.mockReset().mockImplementation((_record: number, itemId: number) => {
    answer((i) => i.id === itemId);
    return Promise.resolve({ data: { upload: { id: 501 }, extraction: { id: 2, status: "queued" } } });
  });
});

function attachment(id: number, filename: string): RecordFile {
  return {
    id, record: RECORD_ID, file: "", filename, uploaded_by: 51, uploaded_by_name: "Ivy Ethics",
    created_at: "2026-09-22T02:00:00Z",
  };
}

function renderFiles(props: Partial<{ owner: boolean; editable: boolean; reviewing: boolean; attach: boolean }> = {}) {
  return renderScreen(
    <FilesSection record={record} owner editable={false} reviewing={false} attach={false} {...props} />,
  );
}

const pdf = (name: string) => new File(["%PDF-1.4"], name, { type: "application/pdf" });

describe("the Files section, for the owner of a record in review", () => {
  it("offers an upload on the requested slot only, and says who asked", async () => {
    const { container } = renderFiles();

    const ethics = await screen.findByRole("region", { name: "Ethics Clearance" });
    expect(within(ethics).getByRole("button", { name: "Upload Ethics Clearance" })).toBeInTheDocument();
    expect(within(ethics).getByText(/Requested by IERC/)).toBeInTheDocument();
    expect(within(ethics).getByText("Requested")).toBeInTheDocument();
    // Nothing asked for, nothing uploaded, and not editable: not listed at all.
    expect(screen.queryByRole("region", { name: "Patent Draft" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Upload Patent Draft" })).not.toBeInTheDocument();
    await expectNoBlockingA11yViolations(container);
  });

  it("uploads into the slot through the dropzone, and the item then reads Uploaded · awaiting review", async () => {
    renderFiles();
    const zone = await screen.findByRole("button", { name: "Upload Ethics Clearance" });
    const file = pdf("ethics.pdf");

    fireEvent.drop(zone, { dataTransfer: { files: [file] } });

    await waitFor(() => expect(upload).toHaveBeenCalledWith(RECORD_ID, ETHICS, file, expect.any(Object)));
    const ethics = screen.getByRole("region", { name: "Ethics Clearance" });
    await waitFor(() => expect(within(ethics).getByText("Uploaded · awaiting review")).toBeInTheDocument());
    expect(within(ethics).queryByRole("button", { name: "Upload Ethics Clearance" })).not.toBeInTheDocument();
  });

  it("answers an Other item, which has no slot, with a dropzone of its own", async () => {
    renderFiles();
    const zone = await screen.findByRole("button", { name: "Upload Consent form" });
    const file = pdf("consent.pdf");

    fireEvent.drop(zone, { dataTransfer: { files: [file] } });

    await waitFor(() => expect(uploadForRequestItem).toHaveBeenCalledWith(RECORD_ID, 12, file, expect.any(Object)));
    const consent = screen.getByRole("region", { name: "Consent form" });
    await waitFor(() => expect(within(consent).getByText("Uploaded · awaiting review")).toBeInTheDocument());
  });

  it("shows an accepted document as Accepted, with nothing more to upload", async () => {
    requests = [openRequest([item({ state: "accepted", state_label: "Accepted", upload: 500 })])];
    renderFiles();

    const ethics = await screen.findByRole("region", { name: "Ethics Clearance" });
    expect(await within(ethics).findByText("Accepted")).toBeInTheDocument();
    expect(within(ethics).queryByRole("button", { name: /^Upload/ })).not.toBeInTheDocument();
  });

  it("shows a rejected upload as Replacement needed, with the reviewer's reason and the upload offered again", async () => {
    requests = [openRequest([item({ rejection_reason: "The scan is unreadable." })])];
    renderFiles();

    const ethics = await screen.findByRole("region", { name: "Ethics Clearance" });
    expect(await within(ethics).findByText("Replacement needed")).toBeInTheDocument();
    expect(within(ethics).getByText(/The scan is unreadable\./)).toBeInTheDocument();
    expect(within(ethics).getByRole("button", { name: "Upload Ethics Clearance" })).toBeInTheDocument();
  });

  it("shows the reason on an item stored as rejected, too", async () => {
    requests = [openRequest([item({ state: "rejected", state_label: "Rejected", rejection_reason: "Wrong form." })])];
    renderFiles();

    const ethics = await screen.findByRole("region", { name: "Ethics Clearance" });
    expect(await within(ethics).findByText("Replacement needed")).toBeInTheDocument();
    expect(within(ethics).getByText(/Wrong form\./)).toBeInTheDocument();
  });

  it("says when an upload fails, and retries without choosing the file again", async () => {
    upload.mockReset().mockRejectedValueOnce({ response: { status: 400, data: { detail: "Only PDF files are accepted." } } });
    renderFiles();
    const file = pdf("ethics.pdf");

    fireEvent.drop(await screen.findByRole("button", { name: "Upload Ethics Clearance" }), {
      dataTransfer: { files: [file] },
    });

    expect(await screen.findByRole("alert")).toHaveTextContent("Only PDF files are accepted.");
    upload.mockResolvedValueOnce({ data: { upload: { id: 500 }, extraction: { id: 1, status: "queued" } } });
    fireEvent.click(screen.getByRole("button", { name: "Retry upload" }));
    await waitFor(() => expect(upload).toHaveBeenCalledTimes(2));
    expect(upload.mock.calls[1][2]).toBe(file);
  });
});

describe("the Files section, for the owner of an editable record", () => {
  it("offers an upload on every slot", async () => {
    requests = [];
    renderFiles({ editable: true });

    expect(await screen.findByRole("button", { name: "Upload Ethics Clearance" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Upload Patent Draft" })).toBeInTheDocument();
  });
});

describe("the Files section, for a reviewer", () => {
  it("offers no upload, and shows each requested document's state", async () => {
    renderFiles({ owner: false, reviewing: true });

    const ethics = await screen.findByRole("region", { name: "Ethics Clearance" });
    expect(await within(ethics).findByText("Requested")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /^Upload/ })).not.toBeInTheDocument();
  });
});

// An office files its own supplementary document (decided 2026-10-06, IR-411):
// offered under `attach_file`, which the adapter grants an office taking part.
describe("supplementary attachments", () => {
  it("lets an office attach a file of any type, and remove it", async () => {
    renderFiles({ owner: false, reviewing: true, attach: true });
    const zone = await screen.findByRole("button", { name: "Attach a supplementary file" });
    const file = new File(["minutes"], "ierc-minutes.docx");

    fireEvent.drop(zone, { dataTransfer: { files: [file] } });

    await waitFor(() => expect(uploadRecordFile).toHaveBeenCalledWith(RECORD_ID, file, expect.any(Object)));
    const remove = await screen.findByRole("button", { name: "Remove ierc-minutes.docx" });
    fireEvent.click(remove);
    await waitFor(() => expect(deleteFile).toHaveBeenCalledWith(70));
    await waitFor(() => expect(screen.queryByText("ierc-minutes.docx")).not.toBeInTheDocument());
  });

  it("lists attachments for download only, to a viewer who may not attach", async () => {
    attachments = [attachment(71, "clearance-certificate.pdf")];
    renderFiles();

    expect(await screen.findByText("clearance-certificate.pdf")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Download clearance-certificate.pdf" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /^Remove clearance/ })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Attach a supplementary file" })).not.toBeInTheDocument();
  });
});
