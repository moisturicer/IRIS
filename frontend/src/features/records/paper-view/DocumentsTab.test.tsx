/**
 * The review page's Documents tab (IR-1203). It was Paper View's Files section
 * (IR-411; spec §4.6, §4.10), which replaced the Documents page and carried
 * over that page's IR-346 tests. IR-1203 draws each document as one row: a
 * row is a group named by its document (it was a region), and a slot's
 * versions open from the row's versions toggle.
 *
 * **One upload path.** Every upload goes through `UploadDropzone`. A
 * reviewer's request for a slot is answered by uploading into that slot the
 * ordinary way (ADR-022 §Amendment 1, IR-346); an "Other" item, which has no
 * slot, takes one of its own. While anything is asked for, every slot takes an
 * upload, and an owner's upload is held, theirs alone with a trash can, until
 * *Submit added documents* or *Submit new version* sends it (ADR-022
 * Amendment 8, IR-1322).
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
import { act, fireEvent, renderScreen, screen, waitFor, within } from "@/test/render";
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

/** The server's answer to a send: every open missing item it answers. */
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

const sendDocuments = vi.fn();

/** An owner's upload to a record in review: held in its slot, answering nothing yet (IR-1322). */
function hold(slotId: number, id: number) {
  slots = slots.map((s) => s.id !== slotId ? s : {
    ...s,
    uploads: [{
      id, record: RECORD_ID, slot: slotId, slot_name: s.name, file: `/media/uploads/9/${id}.pdf`,
      version: s.uploads.length + 1, status: null, status_name: null, uploaded_by: 50,
      uploaded_by_name: "Sam Student", created_at: "2026-10-09T02:00:00Z", reviews: [],
      delete_refused: null, held: true,
    }, ...s.uploads],
  });
}

/** A version already sent (not held), as the server lists it. */
function sentUpload(slotId: number, id: number): RecordUpload {
  return {
    id, record: RECORD_ID, slot: slotId, slot_name: "Patent Draft", file: `/media/uploads/9/${id}.pdf`,
    version: 1, status: null, status_name: null, uploaded_by: 50,
    uploaded_by_name: "Sam Student", created_at: "2026-10-09T02:00:00Z", reviews: [],
    delete_refused: null, held: false,
  } as RecordUpload;
}

/** *Submit added documents*: every held upload is sent and answers what it matches, by slot or name. */
function send() {
  const sent = slots.filter((s) => s.uploads.some((u) => u.held));
  slots = slots.map((s) => ({ ...s, uploads: s.uploads.map((u) => ({ ...u, held: false })) }));
  answer((i) => sent.some((s) => (i.slot != null ? s.id === i.slot : s.name === i.label)));
  return { sent: sent.length, requests_fulfilled: requests.filter((r) => r.state === "fulfilled").length };
}

vi.mock("@/api/records", () => ({
  recordsApi: {
    sendDocuments: (recordId: number) => sendDocuments(recordId),
    documentRequests: () => Promise.resolve({ data: structuredClone(requests) }),
    documentRequestSlots: () => Promise.resolve({ data: [] }),
    uploadManuscript: (recordId: number, file: File, options: unknown) => uploadManuscript(recordId, file, options),
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
  record_type_name: "Thesis / Research",
  abstract_file: "/api/v1/records/9/manuscript/",
  can_request_document: [],
  current_holders: [],
  manuscript_unsubmitted: false,
  revision: { party: null, label: null, blocked: null, withdrawable: null, decision_blocked: null, open: [], new_version: null },
  decision: { party: null, outcomes: [], blocked: null, closes: null, token: null, author_hints: [] },
} as unknown as RecordDetail;

/** A draft: its owner may upload to every slot (IR-1325). */
const drafting = { ...record, pipeline_status: "draft" } as RecordDetail;

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
  deleteFile.mockReset().mockImplementation((fileId: number) => {
    attachments = attachments.filter((f) => f.id !== fileId);
    return Promise.resolve({ data: null });
  });
  slots = [slot(ETHICS, "Ethics Clearance"), slot(PATENT, "Patent Draft")];
  requests = [openRequest([item(), item({ id: 12, slot: null, label: "Consent form" })])];
  upload.mockReset().mockImplementation((_record: number, slotId: number) => {
    hold(slotId, 500);
    return Promise.resolve({ data: { upload: { id: 500 }, extraction: { id: 1, status: "queued" } } });
  });
  // An Other item's file goes into a slot of this record's named for it (ADR-022 §3).
  uploadForRequestItem.mockReset().mockImplementation((_record: number, itemId: number) => {
    const label = requests.flatMap((r) => r.items).find((i) => i.id === itemId)?.label ?? "";
    if (!slots.some((s) => s.name === label)) slots = [...slots, slot(90, label)];
    hold(slots.find((s) => s.name === label)!.id, 501);
    return Promise.resolve({ data: { upload: { id: 501 }, extraction: { id: 2, status: "queued" } } });
  });
  sendDocuments.mockReset().mockImplementation(() => Promise.resolve({ data: send() }));
  deleteUpload.mockReset().mockImplementation((uploadId: number) => {
    slots = slots.map((s) => ({ ...s, uploads: s.uploads.filter((u) => u.id !== uploadId) }));
    return Promise.resolve({ data: null });
  });
});

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
  // Upload only on what was asked for (ADR-022 Amendment 9, IR-1325, replacing IR-1322's every slot).
  it("offers an upload only on what was asked for, and says who asked", async () => {
    const { container } = renderFiles();

    const ethics = await screen.findByRole("group", { name: "Ethics Clearance" });
    expect(within(ethics).getByRole("button", { name: /^Upload Ethics Clearance/ })).toBeInTheDocument();
    expect(within(ethics).getByText(/Requested by IERC/)).toBeInTheDocument();
    expect(within(ethics).getByText("Requested")).toBeInTheDocument();
    // Nobody asked for it, so it is not offered.
    expect(screen.queryByRole("group", { name: "Patent Draft" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /^Upload Patent Draft/ })).not.toBeInTheDocument();
    await expectNoBlockingA11yViolations(container);
  });

  it("shows a file in a slot nobody asked for with no Upload", async () => {
    slots = slots.map((s) => s.id === PATENT ? { ...s, uploads: [sentUpload(PATENT, 610)] } : s);
    renderFiles();

    const patent = await screen.findByRole("group", { name: "Patent Draft" });
    expect(within(patent).getByRole("button", { name: "Download Patent Draft version 1" })).toBeInTheDocument();
    expect(within(patent).queryByRole("button", { name: /^Upload/ })).not.toBeInTheDocument();
  });

  it("lists no unrequested slot, and offers no upload, when nothing is asked for", async () => {
    requests = [];
    renderFiles();

    await screen.findByRole("list", { name: "Documents" });
    expect(screen.queryByRole("group", { name: "Patent Draft" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /^Upload/ })).not.toBeInTheDocument();
  });

  it("holds an upload until Submit added documents, which answers the request", async () => {
    const { container } = renderFiles();
    const zone = await screen.findByRole("button", { name: /^Upload Ethics Clearance/ });
    const file = pdf("ethics.pdf");

    fireEvent.drop(zone, { dataTransfer: { files: [file] } });

    await waitFor(() => expect(upload).toHaveBeenCalledWith(RECORD_ID, ETHICS, file, expect.any(Object)));
    const ethics = screen.getByRole("group", { name: "Ethics Clearance" });
    expect(await within(ethics).findByText("Added, not sent yet")).toBeInTheDocument();
    // Nothing reached IERC yet: the item still reads Requested.
    expect(within(ethics).getByText("Requested")).toBeInTheDocument();
    const bar = screen.getByRole("region", { name: "Changes requested by IERC" });
    expect(bar).toHaveTextContent("1 change not sent yet: Ethics Clearance.");
    await expectNoBlockingA11yViolations(container);

    fireEvent.click(within(bar).getByRole("button", { name: "Submit added documents" }));

    await waitFor(() => expect(sendDocuments).toHaveBeenCalledWith(RECORD_ID));
    expect(await within(ethics).findByText("Uploaded · awaiting review")).toBeInTheDocument();
    expect(within(ethics).queryByText("Added, not sent yet")).not.toBeInTheDocument();
    expect(await screen.findByText("1 document sent to IERC.")).toBeInTheDocument();
  });

  it("answers an Other item, which has no slot, with a dropzone of its own, once sent", async () => {
    renderFiles();
    const zone = await screen.findByRole("button", { name: /^Upload Consent form/ });
    const file = pdf("consent.pdf");

    fireEvent.drop(zone, { dataTransfer: { files: [file] } });

    await waitFor(() => expect(uploadForRequestItem).toHaveBeenCalledWith(RECORD_ID, 12, file, expect.any(Object)));
    const [consent] = await screen.findAllByRole("group", { name: "Consent form" });
    expect(await within(consent).findByText("Added, not sent yet")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Submit added documents" }));

    // The Other row, after the slot named for it, carries the request's state.
    await waitFor(() => expect(within(screen.getAllByRole("group", { name: "Consent form" }).at(-1)!)
      .getByText("Uploaded · awaiting review")).toBeInTheDocument());
  });

  it("removes a held upload with its trash can, even one nobody asked for", async () => {
    hold(PATENT, 600);
    renderFiles();

    const patent = await screen.findByRole("group", { name: "Patent Draft" });
    expect(within(patent).getByText("Added, not sent yet")).toBeInTheDocument();
    fireEvent.click(within(patent).getByRole("button", { name: "Remove Patent Draft version 1" }));
    fireEvent.click(await screen.findByRole("button", { name: "Remove" }));

    await waitFor(() => expect(deleteUpload).toHaveBeenCalledWith(600));
    // Nobody asked for it and it holds no file now, so its row goes (IR-1325).
    await waitFor(() => expect(screen.queryByRole("group", { name: "Patent Draft" })).not.toBeInTheDocument());
  });

  it("keeps Submit added documents grey, saying why, until something is added", async () => {
    renderFiles();

    const bar = await screen.findByRole("region", { name: "Changes requested by IERC" });
    const submit = within(bar).getByRole("button", { name: "Submit added documents" });
    expect(submit).toBeDisabled();
    expect(submit).toHaveAccessibleDescription("Upload what was asked for below, then submit it. Nothing is sent until you do.");
    expect(screen.queryByRole("button", { name: "Submit new version" })).not.toBeInTheDocument();
  });

  it("keeps the held files and says so when the send fails", async () => {
    hold(ETHICS, 600);
    sendDocuments.mockReset().mockRejectedValueOnce({ response: { status: 409, data: { detail: "A revision is open: send these with your new version." } } });
    renderFiles();

    fireEvent.click(await screen.findByRole("button", { name: "Submit added documents" }));

    expect(await screen.findByText("A revision is open: send these with your new version.")).toBeInTheDocument();
    expect(within(screen.getByRole("group", { name: "Ethics Clearance" })).getByText("Added, not sent yet")).toBeInTheDocument();
  });

  it("shows an accepted document as Accepted, with nothing more to upload", async () => {
    requests = [{ ...openRequest([item({ state: "accepted", state_label: "Accepted", upload: 500 })]), state: "fulfilled", state_label: "Fulfilled" }];
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
    renderFiles({ editable: true }, drafting);

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
    renderFiles({ editable: true }, drafting);

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
    renderFiles({ editable: true }, drafting);

    fireEvent.click(await screen.findByRole("button", { name: "Download the Ethics Clearance Template, ethics-form.docx" }));

    await waitFor(() => expect(downloadBlob).toHaveBeenCalledWith(expect.any(Blob), "ethics-form.docx"));
    expect(downloadRequirementTemplate).toHaveBeenCalledWith(ETHICS);
  });

  it("gives a slot that is no longer one of RDCO's requirements no label and no Template", async () => {
    requests = [];
    slots = [...slots, { ...slot(99, "Old Endorsement"), hidden: true, is_required: true, template_name: "old.docx" }];
    renderFiles({ editable: true }, drafting);

    const old = await row("Old Endorsement");
    await within(await row("Ethics Clearance")).findByText("Required");
    expect(within(old).queryByText(/^(Required|Optional)$/)).not.toBeInTheDocument();
    expect(within(old).queryByRole("button", { name: /Template/ })).not.toBeInTheDocument();
  });

  it("says when the labels and Templates didn't load, and still offers every upload", async () => {
    requests = [];
    guidelinesList.mockRejectedValueOnce({ isAxiosError: true, response: { status: 500, data: {} } });
    renderFiles({ editable: true }, drafting);

    expect(await screen.findByText(/labels and the Templates didn't load/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /^Upload Ethics Clearance/ })).toBeInTheDocument();
    expect(within(await row("Ethics Clearance")).queryByText("Required")).not.toBeInTheDocument();
  });

  it("passes axe with labels and Templates shown", async () => {
    requests = [];
    const { container } = renderFiles({ editable: true }, drafting);
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

  // IR-1332: Remove is a trash can alone, like a draft's in My Library: its
  // name says what it removes, and the word "Remove" is its tooltip, not text.
  it("draws Remove as a trash can with no word, and Download with its word", async () => {
    renderFiles({ editable: true }, drafting);
    await openVersions();

    const versions = await screen.findByRole("list", { name: "Versions of Ethics Clearance" });
    expect(within(versions).getByRole("button", { name: "Remove Ethics Clearance version 2" })).toHaveTextContent(/^$/);
    expect(within(versions).getByRole("button", { name: "Download Ethics Clearance version 2" })).toHaveTextContent("Download");
  });

  it("offers no Remove on a kept version, and says why", async () => {
    const { container } = renderFiles({ editable: true }, drafting);
    await openVersions();

    const versions = await screen.findByRole("list", { name: "Versions of Ethics Clearance" });
    expect(within(versions).queryByRole("button", { name: "Remove Ethics Clearance version 1" })).not.toBeInTheDocument();
    expect(within(versions).getByText(/v1 was submitted with this file/)).toBeInTheDocument();
    expect(within(versions).getByRole("button", { name: "Remove Ethics Clearance version 2" })).toBeInTheDocument();
    await expectNoBlockingA11yViolations(container);
  });

  it("asks before removing, and Cancel removes nothing", async () => {
    renderFiles({ editable: true }, drafting);
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
    renderFiles({ editable: true }, drafting);
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
    renderFiles({ editable: true }, drafting);
    await screen.findByRole("button", { name: /^Upload Ethics Clearance/ });
    expect(screen.queryByRole("button", { name: /^Upload revised manuscript/ })).not.toBeInTheDocument();
  });

});

// IR-1318: the Documents tab is where the owner uploads what is asked for and submits.
describe("answering a request in the Documents tab (IR-1318)", () => {
  const ethicsUpload = (id: number) => ({
    id, record: RECORD_ID, slot: ETHICS, slot_name: "Ethics Clearance", file: "/media/uploads/9/ethics.pdf",
    version: 1, status: null, status_name: null, uploaded_by: 50, uploaded_by_name: "Sam Student",
    created_at: "2026-10-09T02:00:00Z", reviews: [], delete_refused: null,
  });
  const inRevision = (unsent: NonNullable<RecordDetail["revision"]["new_version"]>["unsent"], blocked: string | null = null) => ({
    ...record,
    revision: {
      ...record.revision,
      open: [{
        id: 3, party: "ierc", label: "IERC", reason: "Fix the consent section.",
        requested_by: "Ivy Ethics", version: 2, created_at: "2026-10-08T02:00:00Z",
      }],
      new_version: { number: 3, rereview: ["IERC"], kept: ["KTTO"], blocked, unsent },
    },
  } as RecordDetail);

  it("puts Submit new version at the top, naming what is not sent yet", async () => {
    requests = [];
    slots = [{ ...slot(ETHICS, "Ethics Clearance"), uploads: [{ ...ethicsUpload(320), held: true }] }];
    const onSubmit = vi.fn();
    const { container } = renderScreen(
      <DocumentsTab
        record={{ ...inRevision({ manuscript: true, details: false, uploads: [{ id: 320, label: "Ethics Clearance" }] }), manuscript_unsubmitted: true } as RecordDetail}
        owner editable reviewing={false} attach={false} replaceManuscript onSubmitNewVersion={onSubmit}
      />,
    );

    const bar = await screen.findByRole("region", { name: "Changes requested by IERC" });
    expect(bar).toHaveTextContent("2 changes not sent yet: revised manuscript and Ethics Clearance.");
    expect(bar).toHaveTextContent("IERC will review v3. KTTO's clearance is kept.");
    const documents = screen.getByRole("list", { name: "Documents" });
    const [manuscript, ethics] = within(documents).getAllByRole("listitem");
    expect(manuscript).toHaveTextContent("Revised, not yet submitted");
    expect(ethics).toHaveTextContent("Added, not sent yet");

    fireEvent.click(within(bar).getByRole("button", { name: "Submit new version" }));
    expect(onSubmit).toHaveBeenCalledTimes(1);
    await expectNoBlockingA11yViolations(container);
  });

  it("says why it cannot be sent yet, describing the button, before anything changed", async () => {
    requests = [];
    renderScreen(
      <DocumentsTab
        record={inRevision({ manuscript: false, details: false, uploads: [] }, "Nothing has changed since IERC asked for a revision.")}
        owner editable reviewing={false} attach={false} onSubmitNewVersion={vi.fn()}
      />,
    );

    const bar = await screen.findByRole("region", { name: "Changes requested by IERC" });
    expect(bar).not.toHaveTextContent("not sent yet");
    const submit = within(bar).getByRole("button", { name: "Submit new version" });
    expect(submit).toBeDisabled();
    expect(submit).toHaveAccessibleDescription("Nothing has changed since IERC asked for a revision.");
  });

  it("offers no submit to an owner the page gave none, nor to a reviewer", async () => {
    requests = [];
    renderScreen(
      <DocumentsTab record={inRevision({ manuscript: true, details: false, uploads: [] })} owner editable reviewing={false} attach={false} />,
    );
    await screen.findByRole("list", { name: "Documents" });
    expect(screen.queryByRole("button", { name: "Submit new version" })).not.toBeInTheDocument();
  });

  it("names one party once when it asked for a revision and documents, and sends both as the new version", async () => {
    renderScreen(
      <DocumentsTab
        record={inRevision({ manuscript: true, details: false, uploads: [] })}
        owner editable reviewing={false} attach={false} onSubmitNewVersion={vi.fn()}
      />,
    );

    const bar = await screen.findByRole("region", { name: "Changes requested by IERC" });
    expect(within(bar).getByRole("button", { name: "Submit new version" })).toBeEnabled();
    expect(screen.queryByRole("button", { name: "Submit added documents" })).not.toBeInTheDocument();
  });

  it("tells a reviewer nothing about uploading", async () => {
    renderFiles({ owner: false, reviewing: true });

    await screen.findByRole("list", { name: "Documents" });
    expect(screen.queryByRole("region", { name: /Changes requested/ })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Submit added documents" })).not.toBeInTheDocument();
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
