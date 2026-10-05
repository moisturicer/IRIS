/**
 * An owner answers a document request from the Documents page (IR-346,
 * ADR-022 §Amendment 1).
 *
 * A reviewer's request asks for a slot -- "Ethics Clearance" -- and the
 * owner may answer it by uploading into that slot the ordinary way, not only
 * from the Action required panel. The record is in review, which normally
 * shuts the page's upload zones, so the requested slot is the one exception.
 *
 * Which items an upload answers is the server's rule, pinned by the API
 * tests in `apps/documents/tests/test_document_requests.py`. The fake server
 * below answers the way that rule does, so what this file checks is the
 * screen's half: the requested slot offers an upload, the upload goes to that
 * slot, and the panel read afterwards no longer offers the item.
 *
 * Every query goes through the accessible tree, by role and accessible name.
 */
import { Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ActionRequiredPanel } from "@/features/document-requests/ActionRequiredPanel";
import { useAuthStore } from "@/store/auth.store";
import { expectNoBlockingA11yViolations } from "@/test/axe";
import { fireEvent, renderScreen, screen, waitFor, within } from "@/test/render";
import type { User } from "@/types/auth";
import type { SlotWithUploads } from "@/types/documents";
import type { DocumentRequest, RecordDetail } from "@/types/records";

import DocumentsPage from "./DocumentsPage";

const RECORD_ID = 9;
const OWNER_ID = 40;
const ETHICS = 3;
const PATENT = 4;

let requests: DocumentRequest[];
const upload = vi.fn();

/** The server's answer to an owner's slot upload: every open missing item for that slot. */
function answerSlotUpload(slotId: number) {
  requests = requests.map((r) => {
    if (r.state !== "open") return r;
    const items = r.items.map((i) =>
      i.state === "missing" && i.slot === slotId
        ? { ...i, state: "uploaded" as const, state_label: "Uploaded", upload: 500 }
        : i,
    );
    const done = items.every((i) => i.state !== "missing");
    return { ...r, items, state: done ? "fulfilled" : "open", state_label: done ? "Fulfilled" : "Open" };
  });
}

vi.mock("@/api/records", () => ({
  recordsApi: {
    detail: () =>
      Promise.resolve({
        data: {
          id: RECORD_ID,
          pipeline_status: "in_review",
          owners: [{ id: 1, user: OWNER_ID, email: "owner@cit.edu", full_name: "O. Wner", is_primary: true }],
        } as unknown as RecordDetail,
      }),
    documentRequests: () => Promise.resolve({ data: structuredClone(requests) }),
  },
}));
vi.mock("@/api/documents", () => ({
  documentsApi: {
    slotsForRecord: () =>
      Promise.resolve({
        data: [
          { id: ETHICS, name: "Ethics Clearance", record_type: 1, is_required: false, uploads: [] },
          { id: PATENT, name: "Patent Draft", record_type: 1, is_required: false, uploads: [] },
        ] satisfies SlotWithUploads[],
      }),
    files: () => Promise.resolve({ data: [] }),
    upload: (recordId: number, slotId: number, file: File) => upload(recordId, slotId, file),
    uploadForRequestItem: vi.fn(),
  },
}));
vi.mock("@/api/reviews", () => ({ reviewsApi: {} }));

function openRequest(): DocumentRequest {
  return {
    id: 1, party: "ierc", label: "IERC", state: "open", state_label: "Open",
    message: "Please upload the ethics clearance.", requested_by: "Ivy Ethics",
    created_at: "2026-09-20T02:00:00Z", closed_at: null, can_manage: false,
    items: [
      {
        id: 11, slot: ETHICS, label: "Ethics Clearance", state: "missing", state_label: "Missing",
        upload: null, uploaded_at: null, rejection_reason: null, decided_at: null,
      },
      // An "Other" item: no slot, so only the panel can answer it, and it keeps the request open.
      {
        id: 12, slot: null, label: "Consent form", state: "missing", state_label: "Missing",
        upload: null, uploaded_at: null, rejection_reason: null, decided_at: null,
      },
    ],
  };
}

beforeEach(() => {
  requests = [openRequest()];
  upload.mockReset().mockImplementation((_record: number, slotId: number) => {
    answerSlotUpload(slotId);
    return Promise.resolve({ data: { upload: { id: 500 }, extraction: { id: 1, status: "queued" } } });
  });
  useAuthStore.setState({
    user: { id: OWNER_ID, role_name: "Student", is_staff: false, is_superuser: false } as User,
    isAuthenticated: true,
  });
});

function renderDocumentsPage() {
  return renderScreen(
    <Routes>
      <Route path="/records/:id/documents" element={<DocumentsPage />} />
    </Routes>,
    { route: `/records/${RECORD_ID}/documents` },
  );
}

describe("DocumentsPage — a requested slot during review", () => {
  it("offers an upload on the requested slot only, and says who asked", async () => {
    const { container } = renderDocumentsPage();

    expect(await screen.findByRole("button", { name: "Upload Ethics Clearance" })).toBeInTheDocument();
    expect(screen.getByText(/Requested by IERC/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Upload Patent Draft" })).not.toBeInTheDocument();
    await expectNoBlockingA11yViolations(container);
  });

  it("after the upload, the owner's Action required panel no longer offers that item", async () => {
    const page = renderDocumentsPage();
    const zone = await screen.findByRole("button", { name: "Upload Ethics Clearance" });
    const file = new File(["%PDF-1.4"], "ethics.pdf", { type: "application/pdf" });

    fireEvent.drop(zone, { dataTransfer: { files: [file] } });

    await waitFor(() => expect(upload).toHaveBeenCalledWith(RECORD_ID, ETHICS, file));
    await waitFor(() =>
      expect(screen.queryByRole("button", { name: "Upload Ethics Clearance" })).not.toBeInTheDocument(),
    );
    page.unmount();

    // Back on the paper view, the panel reads the requests afresh.
    const { container } = renderScreen(<ActionRequiredPanel recordId={RECORD_ID} />);
    const panel = await screen.findByRole("region", { name: "Action required" });
    const items = within(panel).getByRole("list", { name: /documents requested by IERC/i });
    const [ethics, consent] = within(items).getAllByRole("listitem");
    expect(ethics).toHaveTextContent("Ethics Clearance");
    expect(ethics).toHaveTextContent("Uploaded");
    expect(within(panel).queryByLabelText(/Ethics Clearance/)).not.toBeInTheDocument();
    expect(consent).toHaveTextContent("Missing");
    expect(within(panel).getByLabelText(/Consent form/)).toBeInTheDocument();
    await expectNoBlockingA11yViolations(container);
  });
});
