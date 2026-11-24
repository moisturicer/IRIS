/**
 * The review page's Documents tab (IR-1203). It was Paper View's Files section
 * (IR-411; spec §4.6, §4.10), which replaced the Documents page and carried
 * over that page's IR-346 tests. IR-1203 draws each document as one row: a
 * row is a group named by its document (it was a region), and a slot's
 * versions open from the row's versions toggle.
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

import { emitLiveHint } from "@/lib/live";
import { expectNoBlockingA11yViolations } from "@/test/axe";
import { act, fireEvent, renderScreen, screen, userEvent, waitFor, within } from "@/test/render";
import type { RecordFile, RecordUpload, SlotWithUploads } from "@/types/documents";
import type { DocumentRequest, DocumentRequestItem, RecordDetail } from "@/types/records";

import { DocumentsTab } from "./DocumentsTab";
import type { ReaderDocument } from "./readerDocument";

// Saving is the browser's; what is checked is the name the file is saved under.
const downloadBlob = vi.hoisted(() => vi.fn());
vi.mock("@/lib/utils", async (actual) => ({ ...(await actual<typeof import("@/lib/utils")>()), downloadBlob }));

const RECORD_ID = 9;
const ETHICS = 3;
const PATENT = 4;

let requests: DocumentRequest[];
let slots: SlotWithUploads[];
let attachments: RecordFile[];
const upload = vi.fn();
const uploadForRequestItem = vi.fn();
const uploadRecordFile = vi.fn();
const uploadManuscript = vi.fn();
const deleteFile = vi.fn();
const deleteUpload = vi.fn();
const removeUpload = vi.fn();

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
    uploadManuscript: (recordId: number, file: File, options: unknown) => uploadManuscript(recordId, file, options),
    removeDocumentRequestUpload: (itemId: number, uploadId: number) => removeUpload(itemId, uploadId),
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
    downloadUpload: () => Promise.resolve({ data: new Blob(["file"]) }),
    downloadFile: vi.fn(),
    deleteUpload: (uploadId: number) => deleteUpload(uploadId),
  },
}));

// What RDCO asks a Thesis / Research for (IR-973 reads labels and Templates from Guidelines' list).
const guidelinesList = vi.fn();
const downloadManuscriptTemplate = vi.fn();
const downloadRequirementTemplate = vi.fn();
vi.mock("@/api/guidelines", () => ({
  guidelinesApi: {
    list: () => guidelinesList(),
    downloadManuscriptTemplate: (id: number) => downloadManuscriptTemplate(id),
    downloadRequirementTemplate: (id: number) => downloadRequirementTemplate(id),
  },
}));
const GUIDE = [
  { id: 1, name: "Proposal", description: "", manuscript: { description: "", template_name: "proposal-format.docx" }, requirements: [] },
  {
    id: 2, name: "Thesis / Research", description: "",
    manuscript: { description: "", template_name: "thesis-format.docx" },
    requirements: [
      { id: ETHICS, name: "Ethics Clearance", is_required: true, description: "", template_name: "ethics-form.docx" },
      { id: PATENT, name: "Patent Draft", is_required: false, description: "", template_name: "" },
    ],
  },
];

function item(overrides: Partial<DocumentRequestItem> = {}): DocumentRequestItem {
  return {
    id: 11, slot: ETHICS, label: "Ethics Clearance", state: "missing", state_label: "Missing",
    upload: null, uploaded_at: null, rejection_reason: null, decided_at: null, can_replace: false,
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
  record_type_name: "Thesis / Research",
  abstract_file: "/api/v1/records/9/manuscript/",
  can_request_document: [],
  current_holders: [],
  manuscript_unsubmitted: false,
  revision: { party: null, label: null, blocked: null, withdrawable: null, decision_blocked: null, open: [], new_version: null },
  decision: { party: null, outcomes: [], blocked: null, closes: null, token: null, author_hints: [] },
} as unknown as RecordDetail;

/** A record on the new model with a revision asked for (IR-273): the owner is offered a new version. */
const revising = {
  ...record,
  revision: {
    ...record.revision,
    new_version: { number: 2, rereview: ["IERC"], kept: ["ITSO"], blocked: null },
  },
} as RecordDetail;

function slot(id: number, name: string): SlotWithUploads {
  return {
    id, name, record_type: 1, is_required: false, description: "", position: id, template_name: "",
    hidden: false, uploads: [],
  };
}

beforeEach(() => {
  guidelinesList.mockReset().mockResolvedValue({ data: GUIDE });
  downloadManuscriptTemplate.mockReset().mockResolvedValue({ data: new Blob(["docx"]) });
  downloadRequirementTemplate.mockReset().mockResolvedValue({ data: new Blob(["docx"]) });
  downloadBlob.mockReset();
  attachments = [];
  uploadRecordFile.mockReset().mockImplementation((_record: number, file: File) => {
    // The server says the office that just filed it may remove it.
    attachments = [...attachments, attachment(70, file.name, true)];
    return Promise.resolve({ data: attachments[attachments.length - 1] });
  });
  removeUpload.mockReset().mockResolvedValue({ data: {} });
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

function uploadedAs(id: number, version: number): RecordUpload {
  return {
    id, record: RECORD_ID, slot: ETHICS, slot_name: "Ethics Clearance", file: "x/ethics.pdf", version,
    status: null, status_name: null, uploaded_by: 1, uploaded_by_name: "Rhea Owner",
    created_at: "2026-09-21T02:00:00Z", reviews: [], delete_refused: null,
  };
}

function attachment(id: number, filename: string, canRemove = false): RecordFile {
  return {
    id, record: RECORD_ID, file: "", filename, uploaded_by: 51, uploaded_by_name: "Ivy Ethics",
    created_at: "2026-09-22T02:00:00Z", can_remove: canRemove,
  };
}

function renderFiles(
  props: Partial<{
    owner: boolean; editable: boolean; reviewing: boolean; attach: boolean; replaceManuscript: boolean;
    onOpen: (document: ReaderDocument, opener: HTMLElement) => void;
  }> = {},
  shown: RecordDetail = record,
) {
  return renderScreen(
    <DocumentsTab record={shown} owner editable={false} reviewing={false} attach={false} {...props} />,
  );
}

const pdf = (name: string) => new File(["%PDF-1.4"], name, { type: "application/pdf" });

describe("the Documents tab, for the owner of a record in review", () => {
  it("offers an upload on the requested slot only, and says who asked", async () => {
    const { container } = renderFiles();

    const ethics = await screen.findByRole("group", { name: "Ethics Clearance" });
    expect(within(ethics).getByRole("button", { name: /^Upload Ethics Clearance/ })).toBeInTheDocument();
    expect(within(ethics).getByText(/Requested by IERC/)).toBeInTheDocument();
    expect(within(ethics).getByText("Requested")).toBeInTheDocument();
    // Nothing asked for, nothing uploaded, and not editable: not listed at all.
    expect(screen.queryByRole("group", { name: "Patent Draft" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /^Upload Patent Draft/ })).not.toBeInTheDocument();
    await expectNoBlockingA11yViolations(container);
  });

  it("uploads into the slot through the dropzone, and the item then reads Uploaded · awaiting review", async () => {
    renderFiles();
    const zone = await screen.findByRole("button", { name: /^Upload Ethics Clearance/ });
    const file = pdf("ethics.pdf");

    fireEvent.drop(zone, { dataTransfer: { files: [file] } });

    await waitFor(() => expect(upload).toHaveBeenCalledWith(RECORD_ID, ETHICS, file, expect.any(Object)));
    const ethics = screen.getByRole("group", { name: "Ethics Clearance" });
    await waitFor(() => expect(within(ethics).getByText("Uploaded · awaiting review")).toBeInTheDocument());
    expect(within(ethics).queryByRole("button", { name: /^Upload Ethics Clearance/ })).not.toBeInTheDocument();
  });

  it("answers an Other item, which has no slot, with a dropzone of its own", async () => {
    renderFiles();
    const zone = await screen.findByRole("button", { name: /^Upload Consent form/ });
    const file = pdf("consent.pdf");

    fireEvent.drop(zone, { dataTransfer: { files: [file] } });

    await waitFor(() => expect(uploadForRequestItem).toHaveBeenCalledWith(RECORD_ID, 12, file, expect.any(Object)));
    const consent = screen.getByRole("group", { name: "Consent form" });
    await waitFor(() => expect(within(consent).getByText("Uploaded · awaiting review")).toBeInTheDocument());
  });

  it("replaces an undecided document against its item, and removes it once confirmed", async () => {
    slots[0].uploads = [uploadedAs(500, 1)];
    requests = [openRequest([item({ state: "uploaded", state_label: "Uploaded", upload: 500, can_replace: true })])];
    renderFiles();
    const ethics = await screen.findByRole("group", { name: "Ethics Clearance" });

    // An ordinary slot upload would leave the request on the old file.
    expect(within(ethics).queryByRole("button", { name: /^Upload/ })).not.toBeInTheDocument();
    const file = pdf("better.pdf");
    fireEvent.drop(await within(ethics).findByRole("button", { name: "Replace Ethics Clearance" }), { dataTransfer: { files: [file] } });
    await waitFor(() => expect(uploadForRequestItem).toHaveBeenCalledWith(RECORD_ID, 11, file, expect.objectContaining({ replaces: 500 })));
    expect(upload).not.toHaveBeenCalled();

    requests = [openRequest([item({ state: "uploaded", state_label: "Uploaded", upload: 500, can_replace: true })])];
    await userEvent.click(await within(ethics).findByRole("button", { name: "Remove Ethics Clearance" }));
    const dialog = await screen.findByRole("dialog");
    await userEvent.click(within(dialog).getByRole("button", { name: "Remove" }));
    await waitFor(() => expect(removeUpload).toHaveBeenCalledWith(11, 500));
  });

  it("lists an Other document once, with its file, as one row", async () => {
    slots.push({ ...slots[0], id: 77, name: "Consent form", uploads: [uploadedAs(700, 1)] });
    requests = [openRequest([item({ id: 12, slot: null, label: "Consent form", state: "uploaded", state_label: "Uploaded", upload: 700 })])];
    renderFiles();

    const [consent, ...rest] = await screen.findAllByRole("group", { name: "Consent form" });
    expect(rest).toHaveLength(0);
    expect(within(consent).getByText("Uploaded · awaiting review")).toBeInTheDocument();
    expect(within(consent).getByRole("button", { name: /^Download Consent form/ })).toBeInTheDocument();
  });

  it("shows an accepted document as Accepted, with nothing more to upload", async () => {
    requests = [openRequest([item({ state: "accepted", state_label: "Accepted", upload: 500 })])];
    renderFiles();

    const ethics = await screen.findByRole("group", { name: "Ethics Clearance" });
    expect(await within(ethics).findByText("Accepted")).toBeInTheDocument();
    expect(within(ethics).queryByRole("button", { name: /^Upload/ })).not.toBeInTheDocument();
  });

  it("shows a rejected upload as Replacement needed, with the reviewer's reason and the upload offered again", async () => {
    requests = [openRequest([item({ rejection_reason: "The scan is unreadable." })])];
    renderFiles();

    const ethics = await screen.findByRole("group", { name: "Ethics Clearance" });
    expect(await within(ethics).findByText("Replacement needed")).toBeInTheDocument();
    expect(within(ethics).getByText(/The scan is unreadable\./)).toBeInTheDocument();
    expect(within(ethics).getByRole("button", { name: /^Upload Ethics Clearance/ })).toBeInTheDocument();
  });

  it("shows the reason on an item stored as rejected, too", async () => {
    requests = [openRequest([item({ state: "rejected", state_label: "Rejected", rejection_reason: "Wrong form." })])];
    renderFiles();

    const ethics = await screen.findByRole("group", { name: "Ethics Clearance" });
    expect(await within(ethics).findByText("Replacement needed")).toBeInTheDocument();
    expect(within(ethics).getByText(/Wrong form\./)).toBeInTheDocument();
  });

  it("says when an upload fails, and retries without choosing the file again", async () => {
    upload.mockReset().mockRejectedValueOnce({ response: { status: 400, data: { detail: "Only PDF files are accepted." } } });
    renderFiles();
    const file = pdf("ethics.pdf");

    fireEvent.drop(await screen.findByRole("button", { name: /^Upload Ethics Clearance/ }), {
      dataTransfer: { files: [file] },
    });

    expect(await screen.findByRole("alert")).toHaveTextContent("Only PDF files are accepted.");
    upload.mockResolvedValueOnce({ data: { upload: { id: 500 }, extraction: { id: 1, status: "queued" } } });
    fireEvent.click(screen.getByRole("button", { name: "Retry upload" }));
    await waitFor(() => expect(upload).toHaveBeenCalledTimes(2));
    expect(upload.mock.calls[1][2]).toBe(file);
  });
});

describe("the Documents tab, for the owner of an editable record", () => {
  it("offers an upload on every slot", async () => {
    requests = [];
    renderFiles({ editable: true });

    expect(await screen.findByRole("button", { name: /^Upload Ethics Clearance/ })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /^Upload Patent Draft/ })).toBeInTheDocument();
  });
});

// IR-973 (ADR-063 decision 6): each of RDCO's requirements reads its label and
// offers its Template, from the same row Publish uses.
describe("requirement labels and Templates", () => {
  const row = async (name: string) => screen.findByRole("group", { name });

  it("labels each requirement Required or Optional and offers its Template, and the Manuscript its type's", async () => {
    requests = [];
    renderFiles({ editable: true });

    const ethics = await row("Ethics Clearance");
    expect(await within(ethics).findByText("Required")).toBeInTheDocument();
    expect(within(ethics).getByRole("button", { name: "Download the Ethics Clearance Template, ethics-form.docx" })).toBeInTheDocument();

    const patent = await row("Patent Draft");
    expect(within(patent).getByText("Optional")).toBeInTheDocument();
    expect(within(patent).queryByRole("button", { name: /Template/ })).not.toBeInTheDocument();

    const manuscript = await row("Manuscript");
    expect(within(manuscript).getByText("Required")).toBeInTheDocument();
    expect(within(manuscript).getByRole("button", { name: "Download the Manuscript Template, thesis-format.docx" })).toBeInTheDocument();
  });

  it("downloads a Template under its own file name", async () => {
    requests = [];
    renderFiles({ editable: true });

    fireEvent.click(await screen.findByRole("button", { name: "Download the Ethics Clearance Template, ethics-form.docx" }));

    await waitFor(() => expect(downloadBlob).toHaveBeenCalledWith(expect.any(Blob), "ethics-form.docx"));
    expect(downloadRequirementTemplate).toHaveBeenCalledWith(ETHICS);
  });

  it("gives a slot that is no longer one of RDCO's requirements no label and no Template", async () => {
    requests = [];
    slots = [...slots, { ...slot(99, "Old Endorsement"), hidden: true, is_required: true, template_name: "old.docx" }];
    renderFiles({ editable: true });

    const old = await row("Old Endorsement");
    await within(await row("Ethics Clearance")).findByText("Required");
    expect(within(old).queryByText(/^(Required|Optional)$/)).not.toBeInTheDocument();
    expect(within(old).queryByRole("button", { name: /Template/ })).not.toBeInTheDocument();
  });

  it("says when the labels and Templates didn't load, and still offers every upload", async () => {
    requests = [];
    guidelinesList.mockRejectedValueOnce({ isAxiosError: true, response: { status: 500, data: {} } });
    renderFiles({ editable: true });

    expect(await screen.findByText(/labels and the Templates didn't load/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /^Upload Ethics Clearance/ })).toBeInTheDocument();
    expect(within(await row("Ethics Clearance")).queryByText("Required")).not.toBeInTheDocument();
  });

  it("passes axe with labels and Templates shown", async () => {
    requests = [];
    const { container } = renderFiles({ editable: true });
    await within(await row("Ethics Clearance")).findByText("Required");

    await expectNoBlockingA11yViolations(container);
  });
});

// IR-872 (ADR-058 §2): a file a version names, or one that answered a document
// request, is kept; the server says which. Every other removal asks first.
describe("removing a document version", () => {
  function version(id: number, n: number, refused: string | null): RecordUpload {
    return {
      id, record: RECORD_ID, slot: ETHICS, slot_name: "Ethics Clearance", file: "", version: n,
      status: null, status_name: null, uploaded_by: 50, uploaded_by_name: "Sam Student",
      created_at: "2026-09-22T02:00:00Z", reviews: [], delete_refused: refused,
    };
  }

  beforeEach(() => {
    requests = [];
    deleteUpload.mockReset().mockResolvedValue({ data: null });
    slots = [{
      ...slot(ETHICS, "Ethics Clearance"),
      uploads: [
        version(301, 2, null),
        version(300, 1, "v1 was submitted with this file, so it can't be deleted. Upload a corrected version instead."),
      ],
    }];
  });

  // The versions are one click away (IR-1203).
  const openVersions = async () =>
    fireEvent.click(await screen.findByRole("button", { name: "2 versions of Ethics Clearance" }));

  it("offers no Remove on a kept version, and says why", async () => {
    const { container } = renderFiles({ editable: true });
    await openVersions();

    const versions = await screen.findByRole("list", { name: "Versions of Ethics Clearance" });
    expect(within(versions).queryByRole("button", { name: "Remove Ethics Clearance version 1" })).not.toBeInTheDocument();
    expect(within(versions).getByText(/v1 was submitted with this file/)).toBeInTheDocument();
    expect(within(versions).getByRole("button", { name: "Remove Ethics Clearance version 2" })).toBeInTheDocument();
    await expectNoBlockingA11yViolations(container);
  });

  it("asks before removing, and Cancel removes nothing", async () => {
    renderFiles({ editable: true });
    await openVersions();
    fireEvent.click(await screen.findByRole("button", { name: "Remove Ethics Clearance version 2" }));

    const dialog = await screen.findByRole("dialog", { name: "Remove Ethics Clearance version 2?" });
    fireEvent.click(within(dialog).getByRole("button", { name: "Cancel" }));
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    expect(deleteUpload).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole("button", { name: "Remove Ethics Clearance version 2" }));
    fireEvent.click(within(await screen.findByRole("dialog")).getByRole("button", { name: "Remove" }));
    await waitFor(() => expect(deleteUpload).toHaveBeenCalledWith(301));
  });

  it("keeps the dialog open with the server's reason when a removal is refused", async () => {
    deleteUpload.mockRejectedValueOnce({
      response: { status: 400, data: { detail: "This file answered a document request, so it can't be deleted." } },
    });
    renderFiles({ editable: true });
    await openVersions();
    fireEvent.click(await screen.findByRole("button", { name: "Remove Ethics Clearance version 2" }));
    const dialog = await screen.findByRole("dialog");
    fireEvent.click(within(dialog).getByRole("button", { name: "Remove" }));

    expect(await within(dialog).findByText(/answered a document request/)).toBeInTheDocument();
  });
});

describe("the Documents tab, for a reviewer", () => {
  it("offers no upload, and shows each requested document's state", async () => {
    renderFiles({ owner: false, reviewing: true });

    const ethics = await screen.findByRole("group", { name: "Ethics Clearance" });
    expect(await within(ethics).findByText("Requested")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /^Upload/ })).not.toBeInTheDocument();
  });
});

// An office files its own supplementary document (decided 2026-10-06, IR-411):
// offered under `attach_file`, which the adapter grants an office taking part.
describe("supplementary attachments", () => {
  // Renamed on purpose (IR-1220): "of any type" until supplementary files became
  // PDF, Word, PNG or JPG. The server's check is the one that counts.
  it("offers only PDF, Word, PNG or JPG, and refuses another type before sending it", async () => {
    renderFiles({ owner: false, reviewing: true, attach: true });
    const zone = await screen.findByRole("button", { name: /^Attach a supplementary file/ });
    expect(zone).toHaveAccessibleName(expect.stringContaining("PDF, Word (.docx), PNG or JPG"));

    fireEvent.drop(zone, { dataTransfer: { files: [new File(["<svg/>"], "diagram.svg", { type: "image/svg+xml" })] } });
    expect(await screen.findByText(/diagram\.svg is not an accepted file/)).toBeInTheDocument();
    // Word 97-2003 is re-saved as .docx: a .doc's bytes look like an installer's.
    fireEvent.drop(zone, { dataTransfer: { files: [new File(["ole2"], "minutes.doc", { type: "application/msword" })] } });
    expect(await screen.findByText(/minutes\.doc is not an accepted file/)).toBeInTheDocument();
    expect(uploadRecordFile).not.toHaveBeenCalled();

    const scan = new File(["jpeg"], "signed consent.JPG", { type: "image/jpeg" });
    fireEvent.drop(zone, { dataTransfer: { files: [scan] } });
    await waitFor(() => expect(uploadRecordFile).toHaveBeenCalledWith(RECORD_ID, scan, expect.any(Object)));
  });

  it("lets an office attach a Word file, and remove it", async () => {
    renderFiles({ owner: false, reviewing: true, attach: true });
    const zone = await screen.findByRole("button", { name: /^Attach a supplementary file/ });
    const file = new File(["minutes"], "ierc-minutes.docx");

    fireEvent.drop(zone, { dataTransfer: { files: [file] } });

    await waitFor(() => expect(uploadRecordFile).toHaveBeenCalledWith(RECORD_ID, file, expect.any(Object)));
    const remove = await screen.findByRole("button", { name: "Remove ierc-minutes.docx" });
    fireEvent.click(remove);
    // Changed on purpose (IR-872): every removal now asks first.
    const dialog = await screen.findByRole("dialog", { name: "Remove ierc-minutes.docx?" });
    expect(deleteFile).not.toHaveBeenCalled();
    fireEvent.click(within(dialog).getByRole("button", { name: "Remove" }));
    await waitFor(() => expect(deleteFile).toHaveBeenCalledWith(70));
    await waitFor(() => expect(screen.queryByText("ierc-minutes.docx")).not.toBeInTheDocument());
  });

  // IR-476: a file belongs to the office that filed it. The server decides per
  // file, and the screen offers Remove only where the server will allow it.
  it("offers Remove only on a file the server says this viewer may remove", async () => {
    attachments = [attachment(71, "itso-memo.pdf", true), attachment(72, "ierc-minutes.pdf", false)];
    renderFiles({ owner: false, reviewing: true, attach: true });

    expect(await screen.findByRole("button", { name: "Remove itso-memo.pdf" })).toBeInTheDocument();
    expect(screen.getByText("ierc-minutes.pdf")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Download ierc-minutes.pdf" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Remove ierc-minutes.pdf" })).not.toBeInTheDocument();
  });

  it("lists attachments for download only, to a viewer who may not attach", async () => {
    attachments = [attachment(71, "clearance-certificate.pdf")];
    renderFiles();

    expect(await screen.findByText("clearance-certificate.pdf")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Download clearance-certificate.pdf" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /^Remove clearance/ })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /^Attach a supplementary file/ })).not.toBeInTheDocument();
  });
});

describe("the manuscript, while a revision is asked for (IR-273)", () => {
  beforeEach(() => {
    uploadManuscript.mockReset().mockResolvedValue({ data: {} });
  });

  it("lets the owner upload a revised manuscript for the new version", async () => {
    const onChanged = vi.fn();
    renderScreen(
      <DocumentsTab
        record={revising}
        owner
        editable
        reviewing={false}
        attach={false}
        replaceManuscript
        onChanged={onChanged}
      />,
    );
    const zone = await screen.findByRole("button", { name: /^Upload revised manuscript/ });
    const file = pdf("revised.pdf");

    fireEvent.drop(zone, { dataTransfer: { files: [file] } });

    await waitFor(() => expect(uploadManuscript).toHaveBeenCalledWith(RECORD_ID, file, expect.any(Object)));
    // The page re-reads the record, which now says the manuscript is unsubmitted.
    await waitFor(() => expect(onChanged).toHaveBeenCalled());
  });

  // IR-1048: the manuscript goes up as a PATCH of the record, so DRF refuses it
  // keyed by field, with no `detail`. That reason used to fall through to
  // "Please try again", which no retry can fix.
  it("shows the server's reason when it refuses the manuscript, not Please try again", async () => {
    uploadManuscript.mockReset().mockRejectedValueOnce({
      response: { status: 400, data: { abstract_file: ["This PDF contains unsupported active content."] } },
    });
    renderScreen(
      <DocumentsTab record={revising} owner editable reviewing={false} attach={false} replaceManuscript />,
    );

    fireEvent.drop(await screen.findByRole("button", { name: /^Upload revised manuscript/ }), {
      dataTransfer: { files: [pdf("revised.pdf")] },
    });

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("This PDF contains unsupported active content.");
    expect(alert).not.toHaveTextContent("Please try again");
  });

  it("still says Please try again when the upload fails with no reason, as a dropped connection does", async () => {
    uploadManuscript.mockReset().mockRejectedValueOnce(new Error("Network Error"));
    renderScreen(
      <DocumentsTab record={revising} owner editable reviewing={false} attach={false} replaceManuscript />,
    );

    fireEvent.drop(await screen.findByRole("button", { name: /^Upload revised manuscript/ }), {
      dataTransfer: { files: [pdf("revised.pdf")] },
    });

    expect(await screen.findByRole("alert")).toHaveTextContent("Please try again.");
  });

  it("labels an uploaded manuscript that is not yet submitted", async () => {
    const { container } = renderFiles(
      { editable: true, replaceManuscript: true },
      { ...revising, manuscript_unsubmitted: true } as RecordDetail,
    );

    expect(await screen.findByText("Revised, not yet submitted")).toBeInTheDocument();
    await expectNoBlockingA11yViolations(container);
  });

  it("offers no manuscript upload without the replace_manuscript capability", async () => {
    renderFiles({ editable: true });
    await screen.findByRole("button", { name: /^Upload Ethics Clearance/ });
    expect(screen.queryByRole("button", { name: /^Upload revised manuscript/ })).not.toBeInTheDocument();
  });

});

// IR-1203: a slot's file is saved under its own type, not always as .pdf.
describe("downloading a document version", () => {
  it("saves it under the stored file's own extension", async () => {
    requests = [];
    slots = [{ ...slot(ETHICS, "Ethics Clearance"), uploads: [{
      id: 310, record: RECORD_ID, slot: ETHICS, slot_name: "Ethics Clearance", file: "/media/uploads/9/ethics_scan.PNG",
      version: 2, status: null, status_name: null, uploaded_by: 50, uploaded_by_name: "Sam Student",
      created_at: "2026-09-22T02:00:00Z", reviews: [], delete_refused: null,
    }] }];
    renderFiles({ owner: false, reviewing: true, onOpen: vi.fn() });

    fireEvent.click(await screen.findByRole("button", { name: "Download Ethics Clearance version 2" }));
    await waitFor(() => expect(downloadBlob).toHaveBeenCalledWith(expect.any(Blob), "Ethics Clearance v2.png"));
    // A slot's upload is served as a PDF (IR-1203's image half covers attachments only), so no image Open.
    expect(screen.queryByRole("button", { name: "Open Ethics Clearance version 2" })).not.toBeInTheDocument();
  });

  it("falls back to .pdf when the stored name has no extension", async () => {
    requests = [];
    slots = [{ ...slot(ETHICS, "Ethics Clearance"), uploads: [{
      id: 311, record: RECORD_ID, slot: ETHICS, slot_name: "Ethics Clearance", file: "/media/uploads/9/ethics",
      version: 1, status: null, status_name: null, uploaded_by: 50, uploaded_by_name: "Sam Student",
      created_at: "2026-09-22T02:00:00Z", reviews: [], delete_refused: null,
    }] }];
    renderFiles({ owner: false, reviewing: true });

    fireEvent.click(await screen.findByRole("button", { name: "Download Ethics Clearance version 1" }));
    await waitFor(() => expect(downloadBlob).toHaveBeenCalledWith(expect.any(Blob), "Ethics Clearance v1.pdf"));
  });
});

describe("DocumentsTab, live (ADR-073, IR-1287)", () => {
  it("shows a file someone else added once a hint for its record arrives", async () => {
    attachments = [attachment(71, "clearance-certificate.pdf")];
    renderFiles();
    expect(await screen.findByText("clearance-certificate.pdf")).toBeInTheDocument();

    attachments = [...attachments, attachment(73, "consent-form.pdf")];
    act(() => { emitLiveHint([`record:${RECORD_ID}`]); });

    expect(await screen.findByText("consent-form.pdf")).toBeInTheDocument();
    expect(screen.getByText("clearance-certificate.pdf")).toBeInTheDocument();
  });
});
