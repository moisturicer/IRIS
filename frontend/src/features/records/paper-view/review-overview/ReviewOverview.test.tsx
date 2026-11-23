/**
 * The review on the Overview: the branches, and the owner's files. It carries
 * over what the *Action required* panel (IR-262, IR-471) and the *Revision
 * requested* card's upload (IR-273) were tested for, which it replaced, and
 * adds dropping files and the links into Review.
 *
 * Every query goes through the accessible tree, by role and accessible name.
 */
import { act } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { RequestTimeoutError } from "@/api/requestPolicy";
import type { Capability } from "@/features/records/capabilities";
import { expectNoBlockingA11yViolations } from "@/test/axe";
import { fireEvent, renderScreen, screen, userEvent, waitFor, within } from "@/test/render";
import type { DocumentRequest, RecordDetail, RecordTracker, TrackerPartyRow } from "@/types/records";

import { ReviewOverview } from "./ReviewOverview";

const tracker = vi.fn();
const documentRequests = vi.fn();
const uploadManuscript = vi.fn();
const uploadForRequestItem = vi.fn();
const reviewComments = vi.fn();
const removeUpload = vi.fn();
const discardManuscript = vi.fn();
const downloadUpload = vi.fn();
vi.mock("@/lib/utils", async (original) => ({ ...(await original<object>()), downloadBlob: (...args: unknown[]) => saved(...args) }));
const saved = vi.fn();
vi.mock("@/api/records", () => ({
  recordsApi: {
    tracker: (id: number) => tracker(id),
    documentRequests: (id: number) => documentRequests(id),
    uploadManuscript: (id: number, file: File, options: unknown) => uploadManuscript(id, file, options),
    reviewComments: (id: number) => reviewComments(id),
    removeDocumentRequestUpload: (itemId: number, uploadId: number) => removeUpload(itemId, uploadId),
    discardRevisedManuscript: (id: number) => discardManuscript(id),
    manuscriptBlob: () => Promise.resolve({ data: new Blob(["pdf"]) }),
  },
}));
vi.mock("@/api/documents", () => ({
  documentsApi: {
    uploadForRequestItem: (
      recordId: number, itemId: number, file: File, options?: { onProgress?: (p: number) => void },
    ) => uploadForRequestItem(recordId, itemId, file, options),
    downloadUpload: (uploadId: number) => downloadUpload(uploadId),
  },
}));
const guidelinesList = vi.fn();
const downloadRequirementTemplate = vi.fn();
vi.mock("@/api/guidelines", () => ({
  guidelinesApi: {
    list: () => guidelinesList(),
    downloadRequirementTemplate: (id: number) => downloadRequirementTemplate(id),
  },
}));

const RECORD_ID = 9;

const party = (name: TrackerPartyRow["party"], label: string, extra: Partial<TrackerPartyRow> = {}): TrackerPartyRow => ({
  party: name, label, state: "completed", state_label: "Completed", started: true,
  outcome: "cleared", outcome_label: "Cleared", at: null, preserved: false,
  awaiting_document: false, outcome_earlier: false, in_pool: false, changes_requested: false, seats: null,
  carryover: null, carryover_version: null, carryover_label: null,
  due_at: null, original_due_at: null, is_overdue: false, clock_paused: false, can_extend: false, extensions: [],
  ...extra,
} as TrackerPartyRow);

const PARTIES = [
  party("adviser", "Adviser", { outcome: "approved", outcome_label: "Approved" }),
  party("itso", "ITSO"),
  party("ierc", "IERC", { state: "active", state_label: "Active", outcome: null, outcome_label: null, changes_requested: true }),
  party("ktto", "KTTO", { preserved: true, carryover_label: "Kept from v1" }),
  party("rdco", "RDCO Final", { state: "active", state_label: "Active", outcome: null, outcome_label: null, in_pool: true }),
];
const trackerOf = (parties = PARTIES, extra: Partial<RecordTracker> = {}) =>
  ({ data: { record_id: RECORD_ID, parties, document_requests: [], ...extra } as unknown as RecordTracker });

const item = (id: number, label: string, extra: Partial<DocumentRequest["items"][number]> = {}) => ({
  id, slot: null, label, state: "missing" as const, state_label: "Missing", upload: null, uploaded_at: null,
  rejection_reason: null, decided_at: null, can_replace: false, ...extra,
});
const request = (extra: Partial<DocumentRequest> = {}): DocumentRequest => ({
  id: 1, party: "ierc", label: "IERC", state: "open", state_label: "Open",
  message: "The signed consent forms are missing.", requested_by: "Ivy Ethics",
  created_at: "2026-09-20T02:00:00Z", closed_at: null, can_manage: false,
  items: [item(11, "Ethics Clearance", { slot: 3 })],
  ...extra,
});

const REVISION = {
  id: 3, party: "ierc" as const, label: "IERC", reason: "Add the assent form.", requested_by: "Ivy Ethics",
  version: 2, created_at: "2026-10-08T02:00:00Z",
};
function recordOf(revision: Partial<RecordDetail["revision"]> = {}, extra: Partial<RecordDetail> = {}): RecordDetail {
  return {
    id: RECORD_ID, pipeline_status: "in_review", workflow_state: "awaiting_resubmission",
    workflow_state_label: "Awaiting resubmission", manuscript_unsubmitted: false,
    revision: { party: null, label: null, blocked: null, withdrawable: null, decision_blocked: null, open: [], new_version: null, ...revision },
    ...extra,
  } as unknown as RecordDetail;
}
const asked = (hint: Partial<NonNullable<RecordDetail["revision"]["new_version"]>> = {}, extra: Partial<RecordDetail> = {}) =>
  recordOf({ open: [REVISION], new_version: { number: 3, rereview: ["IERC"], kept: ["ITSO", "KTTO"], blocked: null, ...hint } }, extra);
const REVISER: Capability[] = ["create_version", "replace_manuscript", "edit_details"];

function show(record: RecordDetail, { can = REVISER, owner = true }: { can?: Capability[]; owner?: boolean } = {}) {
  const props = { onOpenReview: vi.fn(), onSubmitNewVersion: vi.fn(), onDocumentsChanged: vi.fn() };
  const view = renderScreen(
    <ReviewOverview record={record} can={new Set(can)} userIsOwner={owner} trackerVersion={0} {...props} />,
  );
  return { ...props, ...view };
}
const pdf = (name = "file.pdf") => new File(["%PDF-1.7"], name, { type: "application/pdf" });
const drop = (target: Element, ...files: File[]) => fireEvent.drop(target, { dataTransfer: { files } });
const fileRow = (label: string) => {
  const list = screen.getByRole("list", { name: "Requested files" });
  return within(list).getByText(label).closest("li") as HTMLElement;
};
const node = (name: string) => screen.getByRole("heading", { level: 3, name }).closest("[data-branch]") as HTMLElement;

beforeEach(() => {
  tracker.mockReset().mockResolvedValue(trackerOf());
  documentRequests.mockReset().mockResolvedValue({ data: [] });
  uploadManuscript.mockReset().mockResolvedValue({ data: {} });
  uploadForRequestItem.mockReset().mockResolvedValue({ data: {} });
  reviewComments.mockReset().mockResolvedValue({ data: [] });
  removeUpload.mockReset().mockResolvedValue({ data: {} });
  discardManuscript.mockReset().mockResolvedValue({ data: {} });
  downloadUpload.mockReset().mockResolvedValue({ data: new Blob(["pdf"]) });
  saved.mockReset();
  guidelinesList.mockReset().mockResolvedValue({ data: [{
    id: 2, name: "Thesis / Research", description: "", manuscript: { description: "", template_name: "" },
    requirements: [{ id: 3, name: "Ethics Clearance", is_required: true, description: "", template_name: "ethics-form.docx" }],
  }] });
  downloadRequirementTemplate.mockReset().mockResolvedValue({ data: new Blob(["docx"]) });
});

describe("the branches", () => {
  it("stands the offices side by side, with each party's state in the server's words", async () => {
    const { container } = show(asked());

    const offices = await screen.findByRole("list", { name: "Offices" });
    expect(within(offices).getAllByRole("heading").map((h) => h.textContent)).toEqual(["ITSO", "IERC", "KTTO"]);
    expect(node("ITSO")).toHaveTextContent("Cleared");
    expect(node("IERC")).toHaveTextContent("Changes requested");
    expect(node("KTTO")).toHaveTextContent("Kept from v1");
    expect(node("RDCO Final")).toHaveTextContent("Active · Unassigned");
    await expectNoBlockingA11yViolations(container);
  });

  it("puts each request's words with who asked, and opens them in Review", async () => {
    documentRequests.mockResolvedValue({ data: [request({ party: "itso", label: "ITSO", message: "Send the search again." })] });
    const { onOpenReview } = show(asked());

    await screen.findByText("Send the search again.");
    expect(node("IERC")).toHaveTextContent("Asked for changes · on v2");
    expect(node("IERC")).toHaveTextContent("Add the assent form.");
    expect(node("ITSO")).toHaveTextContent("Asked for a document");

    await userEvent.click(screen.getByRole("button", { name: "Read in Review: IERC's request" }));
    expect(onOpenReview).toHaveBeenLastCalledWith({ tab: "conversation", party: "ierc" });
    await userEvent.click(screen.getByRole("button", { name: "Read in Review: what ITSO asked for" }));
    expect(onOpenReview).toHaveBeenLastCalledWith({ tab: "documents", party: null });
    await userEvent.click(screen.getByRole("button", { name: "See review history" }));
    expect(onOpenReview).toHaveBeenLastCalledWith();
  });

  it("holds several requests from one office on its one card", async () => {
    documentRequests.mockResolvedValue({ data: [
      request({ message: "First." }),
      request({ id: 2, message: "Second.", items: [item(21, "Form A"), item(22, "Form B")] }),
    ] });
    show(asked());

    await screen.findByText("Second.");
    const ierc = node("IERC");
    expect(ierc).toHaveTextContent("Add the assent form.");
    expect(ierc).toHaveTextContent("First.");
    expect(ierc).toHaveTextContent("Asked for 2 documents");
  });

  it("opens a long request in place", async () => {
    const reason = `${"Please correct the consent section. ".repeat(12)}The end.`;
    show(recordOf({ open: [{ ...REVISION, reason }] }));

    await screen.findByRole("list", { name: "Offices" });
    expect(node("IERC")).not.toHaveTextContent("The end.");
    await userEvent.click(screen.getByRole("button", { name: "See more of IERC's request" }));
    expect(node("IERC")).toHaveTextContent("The end.");
    expect(screen.queryByRole("button", { name: /See more/ })).not.toBeInTheDocument();
  });

  it("renders a reviewer's words as text, never as markup", async () => {
    const { container } = show(recordOf({ open: [{ ...REVISION, reason: "<b>Bold</b> <img src=x onerror=alert(1)>" }] }));

    await screen.findByRole("list", { name: "Offices" });
    expect(screen.getByText("<b>Bold</b> <img src=x onerror=alert(1)>")).toBeInTheDocument();
    // Structural on purpose: an absent element has no role to find.
    expect(container.querySelector("b")).toBeNull();
    expect(container.querySelector("img")).toBeNull();
  });

  it("still shows the owner the request, and Try again, when the tracker fails", async () => {
    tracker.mockRejectedValueOnce(new RequestTimeoutError(30_000)).mockResolvedValue(trackerOf());
    show(asked());

    expect(await screen.findByRole("alert")).toHaveTextContent("took too long");
    expect(screen.getByText("Add the assent form.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Submit new version" })).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Retry" }));
    expect(await screen.findByRole("list", { name: "Offices" })).toBeInTheDocument();
  });

  it("shows a reviewer the same branches with no files of the owner's, and asks the server for none", async () => {
    show(asked(), { owner: false, can: [] });

    await screen.findByRole("list", { name: "Offices" });
    expect(node("IERC")).toHaveTextContent("Add the assent form.");
    expect(screen.queryByRole("list", { name: "Requested files" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Submit new version" })).not.toBeInTheDocument();
    expect(documentRequests).not.toHaveBeenCalled();
  });

  it("leaves out a party the record does not need, and draws an Adviser alone", async () => {
    tracker.mockResolvedValue(trackerOf([
      party("adviser", "Adviser", { state: "active", state_label: "Active", outcome: null, outcome_label: null }),
      party("rdco", "RDCO Final", { state: "not_required", state_label: "Not required", outcome: null, outcome_label: null }),
    ]));
    show(recordOf());

    expect(await screen.findByRole("heading", { level: 3, name: "Adviser" })).toBeInTheDocument();
    expect(screen.queryByText("RDCO Final")).not.toBeInTheDocument();
    expect(screen.queryByRole("list", { name: "Offices" })).not.toBeInTheDocument();
  });
});

describe("the owner's new version", () => {
  it("says who reviews it and whose clearance is kept, and opens Submit", async () => {
    const { onSubmitNewVersion } = show(asked());

    const panel = await screen.findByRole("region", { name: "Your new version" });
    expect(panel).toHaveTextContent("IERC will review v3. ITSO and KTTO keep their clearances.");
    await userEvent.click(within(panel).getByRole("button", { name: "Submit new version" }));
    expect(onSubmitNewVersion).toHaveBeenCalledOnce();
  });

  it("takes the revised manuscript dropped on the field, and has the page read the record again", async () => {
    const { onDocumentsChanged } = show(asked());

    const file = pdf("revised.pdf");
    const zone = await screen.findByRole("button", { name: /^Upload Revised manuscript/ });
    expect(zone).toHaveTextContent("Revised manuscript. PDF, up to 50 MB");
    drop(zone, file);

    await waitFor(() => expect(onDocumentsChanged).toHaveBeenCalled());
    expect(uploadManuscript).toHaveBeenCalledWith(RECORD_ID, file, expect.anything());
    expect(screen.getAllByRole("status").some((s) => s.textContent === "revised.pdf uploaded")).toBe(true);
  });

  it("says a stored manuscript is not submitted yet, and offers to replace it", async () => {
    show(asked({}, { manuscript_unsubmitted: true }));

    await screen.findByRole("region", { name: "Your new version" });
    expect(fileRow("Revised manuscript")).toHaveTextContent("Ready, not yet submitted");
    drop(screen.getByRole("button", { name: "Replace Revised manuscript" }), pdf("again.pdf"));
    await waitFor(() => expect(uploadManuscript).toHaveBeenCalledOnce());
  });

  it("downloads and, once confirmed, throws away a stored manuscript", async () => {
    const { onDocumentsChanged } = show(asked({}, { manuscript_unsubmitted: true }), {
      can: [...REVISER, "discard_revised_manuscript"],
    });

    await userEvent.click(await screen.findByRole("button", { name: "Download Revised manuscript" }));
    await waitFor(() => expect(saved).toHaveBeenCalledWith(expect.any(Blob), "Revised manuscript.pdf"));

    await userEvent.click(screen.getByRole("button", { name: "Remove Revised manuscript" }));
    const dialog = await screen.findByRole("dialog", { name: "Remove Revised manuscript?" });
    expect(discardManuscript).not.toHaveBeenCalled();
    await userEvent.click(within(dialog).getByRole("button", { name: "Remove" }));
    await waitFor(() => expect(discardManuscript).toHaveBeenCalledWith(RECORD_ID));
    await waitFor(() => expect(onDocumentsChanged).toHaveBeenCalled());
  });

  it("offers no manuscript upload without the capability", async () => {
    show(asked(), { can: ["create_version"] });

    await screen.findByRole("region", { name: "Your new version" });
    expect(screen.queryByText("Revised manuscript")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /^Upload/ })).not.toBeInTheDocument();
  });

  it("shows the server's refusal, and refuses a file that is not a PDF before sending it", async () => {
    uploadManuscript.mockRejectedValue({ response: { data: { abstract_file: ["Unsupported active content."] } } });
    show(asked());

    const zone = await screen.findByRole("button", { name: /^Upload Revised manuscript/ });
    drop(zone, new File(["x"], "notes.docx", { type: "application/msword" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("notes.docx is not an accepted file");
    expect(uploadManuscript).not.toHaveBeenCalled();

    drop(zone, pdf("active.pdf"));
    expect(await screen.findByText(/Unsupported active content/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Retry upload" })).toBeInTheDocument();
  });

  it("says what still holds the new version", async () => {
    show(asked({ blocked: "Nothing has changed since IERC asked for a revision." }));

    expect(await screen.findByRole("button", { name: "Submit new version" }))
      .toHaveAccessibleDescription("Nothing has changed since IERC asked for a revision.");
  });
});

describe("the review's comments", () => {
  const comment = (id: number, extra: object = {}) => ({
    id, reply_to: null, is_draft: false, version: 1, author: 2, author_name: "Ivy Ethics", party_label: "IERC", kind: "thread",
    body: `Comment ${id}`, severity: "must_fix", status: "open", status_label: "Open", state: "open",
    anchor: { version: 1, page: 4, quote: "respondents", regions: [] }, document: null, answer: null, replies: [],
    resolved_at: null, sent_at: "2026-11-01T00:00:00Z", created_at: "2026-11-01T00:00:00Z", ...extra,
  });
  const readable = { readiness: {} } as never;

  it("shows every open comment, whole, and opens its thread in Review", async () => {
    reviewComments.mockResolvedValue({ data: [
      comment(1, { severity: "suggestion", body: "Cite the survey." }),
      comment(2, { body: `${"Say when the survey ran. ".repeat(20)}The end.` }),
    ] });
    const { onOpenReview, container } = show(recordOf({}, readable), { owner: false });

    const list = await screen.findByRole("list", { name: "Comments" });
    const rows = within(list).getAllByRole("listitem");
    // Must fix first, and never cut.
    expect(rows[0]).toHaveTextContent("The end.");
    expect(rows[0]).toHaveTextContent("Must fix");
    expect(rows[1]).toHaveTextContent("Cite the survey.");
    expect(within(list).queryByRole("textbox")).not.toBeInTheDocument();
    await userEvent.click(within(rows[1]).getByRole("button"));
    expect(onOpenReview).toHaveBeenCalledWith({ tab: "threads", party: null, thread: 1 });
    await expectNoBlockingA11yViolations(container);
  });

  it("asks nothing of a viewer who may not read the review, and draws nothing with none open", async () => {
    show(recordOf({}, { readiness: null } as never), { owner: false });
    await screen.findByRole("list", { name: "Offices" });
    expect(reviewComments).not.toHaveBeenCalled();
    expect(screen.queryByRole("heading", { name: "Comments" })).not.toBeInTheDocument();
  });
});

describe("a document already handed in", () => {
  const sent = (extra: object = {}) => request({
    state: "fulfilled", state_label: "Fulfilled",
    items: [item(11, "Ethics Clearance", { slot: 3, state: "uploaded", state_label: "Uploaded", upload: 40, can_replace: true, ...extra })],
  });
  const owner = { can: [] as Capability[] };

  it("can be downloaded, replaced and removed until it is decided", async () => {
    documentRequests.mockResolvedValue({ data: [sent()] });
    const { container } = show(recordOf(), owner);

    await userEvent.click(await screen.findByRole("button", { name: "Download Ethics Clearance" }));
    await waitFor(() => expect(downloadUpload).toHaveBeenCalledWith(40));
    expect(fileRow("Ethics Clearance")).toHaveTextContent("Uploaded · awaiting review");

    const better = pdf("better.pdf");
    drop(screen.getByRole("button", { name: "Replace Ethics Clearance" }), better);
    await waitFor(() => expect(uploadForRequestItem).toHaveBeenCalledWith(
      RECORD_ID, 11, better, expect.objectContaining({ replaces: 40 })));

    await userEvent.click(await screen.findByRole("button", { name: "Remove Ethics Clearance" }));
    const dialog = await screen.findByRole("dialog", { name: "Remove Ethics Clearance?" });
    documentRequests.mockResolvedValue({ data: [request()] });
    await userEvent.click(within(dialog).getByRole("button", { name: "Remove" }));
    await waitFor(() => expect(removeUpload).toHaveBeenCalledWith(11, 40));
    expect(await screen.findByRole("button", { name: /^Upload Ethics Clearance/ })).toBeInTheDocument();
    await expectNoBlockingA11yViolations(container);
  });

  it("keeps the file and says why when the server refuses", async () => {
    documentRequests.mockResolvedValue({ data: [sent()] });
    removeUpload.mockRejectedValue({ response: { data: { detail: "That document has been accepted, so it can't be changed." } } });
    show(recordOf(), owner);

    await userEvent.click(await screen.findByRole("button", { name: "Remove Ethics Clearance" }));
    const dialog = await screen.findByRole("dialog");
    await userEvent.click(within(dialog).getByRole("button", { name: "Remove" }));
    expect(await within(dialog).findByText(/has been accepted/)).toBeInTheDocument();
    await userEvent.click(within(dialog).getByRole("button", { name: "Cancel" }));
    expect(screen.getByRole("button", { name: "Download Ethics Clearance" })).toBeInTheDocument();
  });

  it("is only read once decided", async () => {
    documentRequests.mockResolvedValue({ data: [
      request({ items: [item(11, "Ethics Clearance", { state: "accepted", state_label: "Accepted", upload: 40 }), item(12, "Data sheet")] }),
    ] });
    show(recordOf(), owner);

    const row = (await screen.findByRole("button", { name: "Download Ethics Clearance" })).closest("li") as HTMLElement;
    expect(row).toHaveTextContent("Accepted");
    expect(within(row).queryByRole("button", { name: /Replace|Remove/ })).not.toBeInTheDocument();
  });
});

describe("the documents reviewers asked for", () => {
  const two = () => request({ items: [item(11, "Ethics Clearance", { slot: 3 }), item(13, "Data sheet")] });
  const owner = { can: [] as Capability[] };

  it("sends the only missing document from the field, against its item", async () => {
    documentRequests.mockResolvedValue({ data: [request()] });
    show(recordOf(), owner);

    const file = pdf("ethics.pdf");
    drop(await screen.findByRole("button", { name: /^Upload Ethics Clearance/ }), file);
    await waitFor(() => expect(uploadForRequestItem).toHaveBeenCalledWith(RECORD_ID, 11, file, expect.anything()));
  });

  it("asks which file is which when several are dropped on the field, and never guesses from the name", async () => {
    documentRequests.mockResolvedValue({ data: [two()] });
    show(recordOf(), owner);

    const sheet = pdf("data-sheet.pdf");
    const ethics = pdf("ethics-clearance.pdf");
    drop(await screen.findByRole("button", { name: /^Upload files/ }), sheet, ethics);
    expect(uploadForRequestItem).not.toHaveBeenCalled();

    const waiting = screen.getByRole("list", { name: "Files to place" });
    expect(within(waiting).getAllByRole("listitem")).toHaveLength(2);
    await userEvent.selectOptions(screen.getByRole("combobox", { name: "Which file is data-sheet.pdf?" }), "Data sheet (IERC)");
    await waitFor(() => expect(uploadForRequestItem).toHaveBeenCalledWith(RECORD_ID, 13, sheet, expect.anything()));
    expect(screen.queryByText("data-sheet.pdf", { selector: "li > span" })).not.toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "Remove ethics-clearance.pdf" }));
    expect(screen.queryByRole("list", { name: "Files to place" })).not.toBeInTheDocument();
    expect(uploadForRequestItem).toHaveBeenCalledTimes(1);
  });

  it("sends a file dropped on a row to that row, once, even over its own button", async () => {
    documentRequests.mockResolvedValue({ data: [two()] });
    show(recordOf(), owner);

    await screen.findByRole("list", { name: "Requested files" });
    const ethics = pdf("a.pdf");
    drop(fileRow("Ethics Clearance"), ethics);
    await waitFor(() => expect(uploadForRequestItem).toHaveBeenCalledWith(RECORD_ID, 11, ethics, expect.anything()));

    const sheet = pdf("b.pdf");
    drop(within(fileRow("Data sheet")).getByRole("button", { name: /Upload Data sheet/ }), sheet);
    await waitFor(() => expect(uploadForRequestItem).toHaveBeenCalledWith(RECORD_ID, 13, sheet, expect.anything()));
    expect(uploadForRequestItem).toHaveBeenCalledTimes(2);
  });

  it("refuses two files, or one that is not a PDF, on a row", async () => {
    documentRequests.mockResolvedValue({ data: [two()] });
    show(recordOf(), owner);

    await screen.findByRole("list", { name: "Requested files" });
    drop(fileRow("Data sheet"), pdf("a.pdf"), pdf("b.pdf"));
    expect(await screen.findByRole("alert")).toHaveTextContent("Data sheet takes one file.");
    drop(fileRow("Data sheet"), new File(["x"], "notes.docx"));
    expect(await screen.findByRole("alert")).toHaveTextContent("notes.docx is not an accepted file");
    expect(uploadForRequestItem).not.toHaveBeenCalled();
  });

  it("shows progress, offers no second upload meanwhile, and says when it is in", async () => {
    documentRequests.mockResolvedValue({ data: [two()] });
    let progress: ((percent: number) => void) | undefined;
    let finish: (value: unknown) => void = () => {};
    uploadForRequestItem.mockImplementation((_r, _i, _f, options) => {
      progress = options?.onProgress;
      return new Promise((resolve) => { finish = resolve; });
    });
    const { container } = show(recordOf(), owner);

    await screen.findByRole("list", { name: "Requested files" });
    drop(fileRow("Ethics Clearance"), pdf("ethics.pdf"));
    const bar = await screen.findByRole("progressbar", { name: "Uploading ethics.pdf" });
    act(() => progress?.(42.4));
    expect(bar).toHaveAttribute("aria-valuenow", "42");
    drop(fileRow("Ethics Clearance"), pdf("again.pdf"));
    expect(uploadForRequestItem).toHaveBeenCalledTimes(1);
    await expectNoBlockingA11yViolations(container);

    await act(async () => finish({ data: {} }));
    expect(screen.getAllByRole("status").some((s) => s.textContent === "ethics.pdf uploaded")).toBe(true);
  });

  it("keeps a running upload when another's refresh fails, and says the refresh failed", async () => {
    documentRequests.mockResolvedValueOnce({ data: [two()] }).mockRejectedValueOnce(new Error("Network Error"));
    const settle: Record<number, (v: unknown) => void> = {};
    uploadForRequestItem.mockImplementation((_r, id: number) => new Promise((ok) => { settle[id] = ok; }));
    show(recordOf(), owner);

    await screen.findByRole("list", { name: "Requested files" });
    drop(fileRow("Ethics Clearance"), pdf("ethics.pdf"));
    drop(fileRow("Data sheet"), pdf("data.pdf"));
    await act(async () => settle[11]({ data: {} }));

    expect(await screen.findByText(/could not refresh/i)).toBeInTheDocument();
    expect(screen.getByRole("progressbar", { name: "Uploading data.pdf" })).toBeInTheDocument();
  });

  it("keeps a running upload when the tracker arrives, and when who asks changes", async () => {
    let arrive: (v: unknown) => void = () => {};
    tracker.mockReturnValue(new Promise((ok) => { arrive = ok; }));
    documentRequests.mockResolvedValueOnce({ data: [
      request({ party: "itso", label: "ITSO", items: [item(11, "Search")] }),
      request({ id: 2, party: "adviser", label: "Adviser", items: [item(13, "Endorsement")] }),
    ] }).mockResolvedValue({ data: [request({ id: 2, party: "adviser", label: "Adviser", items: [item(13, "Endorsement")] })] });
    const settle: Record<number, (v: unknown) => void> = {};
    uploadForRequestItem.mockImplementation((_r, id: number) => new Promise((ok) => { settle[id] = ok; }));
    show(recordOf(), owner);

    await screen.findByRole("list", { name: "Requested files" });
    drop(fileRow("Endorsement"), pdf("endorsement.pdf"));
    drop(fileRow("Search"), pdf("search.pdf"));
    await act(async () => arrive(trackerOf()));
    expect(screen.getByRole("progressbar", { name: "Uploading endorsement.pdf" })).toBeInTheDocument();

    // ITSO's request closes, so the panel moves up under the Adviser.
    await act(async () => settle[11]({ data: {} }));
    await waitFor(() => expect(screen.queryByText("Search")).not.toBeInTheDocument());
    expect(screen.getByRole("progressbar", { name: "Uploading endorsement.pdf" })).toBeInTheDocument();
  });

  it("retries a failed upload with the same file", async () => {
    documentRequests.mockResolvedValue({ data: [request()] });
    uploadForRequestItem.mockRejectedValueOnce({ response: { data: { detail: "The server is busy." } } });
    show(recordOf(), owner);

    const file = pdf("ethics.pdf");
    drop(await screen.findByRole("button", { name: /^Upload Ethics Clearance/ }), file);
    await userEvent.click(await screen.findByRole("button", { name: "Retry upload" }));
    await waitFor(() => expect(uploadForRequestItem).toHaveBeenCalledTimes(2));
    expect(uploadForRequestItem.mock.calls[1].slice(0, 3)).toEqual([RECORD_ID, 11, file]);
  });

  it("says the request is fulfilled after its last upload, and takes no more files", async () => {
    const single = request();
    documentRequests.mockResolvedValueOnce({ data: [single] }).mockResolvedValue({ data: [{
      ...single, state: "fulfilled", state_label: "Fulfilled", items: [{ ...single.items[0], state: "uploaded", state_label: "Uploaded" }],
    }] });
    show(recordOf(), owner);

    drop(await screen.findByRole("button", { name: /^Upload Ethics Clearance/ }), pdf());
    const panel = await screen.findByRole("region", { name: "Requested documents" });
    expect(panel).toHaveTextContent("Fulfilled. IERC has been told everything is uploaded.");
    expect(fileRow("Ethics Clearance")).toHaveTextContent("Uploaded · awaiting review");
    expect(within(panel).queryByRole("button", { name: /Upload/ })).not.toBeInTheDocument();
  });

  it("says why an upload was turned down, and takes a replacement", async () => {
    documentRequests.mockResolvedValue({ data: [request({ items: [item(11, "Ethics Clearance", { rejection_reason: "The scan is unreadable." })] })] });
    show(recordOf(), owner);

    await screen.findByRole("list", { name: "Requested files" });
    expect(fileRow("Ethics Clearance")).toHaveTextContent("IERC did not accept your last upload: “The scan is unreadable.”");
    expect(fileRow("Ethics Clearance")).toHaveTextContent("Replacement needed");
    expect(screen.getByRole("button", { name: /^Upload Ethics Clearance/ })).toBeInTheDocument();
  });

  it("offers the requested slot's Template, and none for an Other item", async () => {
    documentRequests.mockResolvedValue({ data: [two()] });
    show(recordOf(), owner);

    const template = await screen.findByRole("button", { name: "Download the Ethics Clearance Template, ethics-form.docx" });
    expect(within(fileRow("Data sheet")).queryByRole("button", { name: /Template/ })).not.toBeInTheDocument();
    fireEvent.click(template);
    await waitFor(() => expect(downloadRequirementTemplate).toHaveBeenCalledWith(3));
  });

  it("shows none for a request that is closed or withdrawn", async () => {
    documentRequests.mockResolvedValue({ data: [
      request({ state: "fulfilled", state_label: "Fulfilled" }), request({ id: 2, state: "withdrawn", state_label: "Withdrawn" }),
    ] });
    show(recordOf(), owner);

    await screen.findByRole("list", { name: "Offices" });
    expect(screen.queryByRole("list", { name: "Requested files" })).not.toBeInTheDocument();
  });

  it("says so when the requests cannot be loaded, instead of showing nothing", async () => {
    documentRequests.mockRejectedValue(new Error("Network Error"));
    show(recordOf(), owner);

    expect(await screen.findByText(/could not load the documents reviewers asked for/i)).toBeInTheDocument();
  });
});
