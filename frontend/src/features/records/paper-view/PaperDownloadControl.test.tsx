/**
 * IR-677: the paper page's download control, one test per state the server
 * can report (ADR-048). The control picks what to show from `download` alone
 * and saves a copy only through the download route, never the reader's bytes.
 */
import { beforeEach, describe, expect, it, vi } from "vitest";

import { expectNoBlockingA11yViolations } from "@/test/axe";
import { render, screen, userEvent, waitFor } from "@/test/render";
import type { DownloadState } from "@/types/records";

import { PaperDownloadControl } from "./PaperDownloadControl";

const downloadCopy = vi.fn();
const requestDownload = vi.fn();
const downloadBlob = vi.fn();
const addToast = vi.fn();

vi.mock("@/api/records", () => ({
  recordsApi: {
    downloadCopy: (...args: unknown[]) => downloadCopy(...args),
    requestDownload: (...args: unknown[]) => requestDownload(...args),
  },
}));

vi.mock("@/lib/utils", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/utils")>()),
  downloadBlob: (...args: unknown[]) => downloadBlob(...args),
}));

vi.mock("@/store/ui.store", () => ({
  useUIStore: (select: (s: { addToast: typeof addToast }) => unknown) => select({ addToast }),
}));

function state(overrides: Partial<DownloadState>): DownloadState {
  return {
    state: "none",
    allowed: false,
    message: "Request a download of this paper to save a copy.",
    grant_expires_at: null,
    request: null,
    ...overrides,
  };
}

function renderControl(download: DownloadState | null, onChanged = vi.fn()) {
  const view = render(
    <PaperDownloadControl recordId={7} recordTitle="A published thesis" download={download} onChanged={onChanged} />,
  );
  return { ...view, onChanged };
}

beforeEach(() => {
  downloadCopy.mockReset();
  requestDownload.mockReset();
  downloadBlob.mockReset();
  addToast.mockReset();
});

describe("a reader who may download", () => {
  it("saves a marked copy through the download route when exempt", async () => {
    const pdf = new Blob(["%PDF-"], { type: "application/pdf" });
    downloadCopy.mockResolvedValue({
      data: pdf,
      headers: { "content-disposition": 'attachment; filename="A published thesis.pdf"' },
    });
    const { container } = renderControl(state({ state: "exempt", allowed: true, message: "You may download." }));

    await userEvent.click(screen.getByRole("button", { name: "Download" }));

    expect(downloadCopy).toHaveBeenCalledWith(7);
    await waitFor(() => expect(downloadBlob).toHaveBeenCalledWith(pdf, "A published thesis.pdf"));
    expect(screen.queryByText(/access until/i)).not.toBeInTheDocument();
    await expectNoBlockingA11yViolations(container);
  });

  it("says until when a granted reader may download", async () => {
    const { container } = renderControl(
      state({ state: "granted", allowed: true, grant_expires_at: "2026-11-30T08:00:00Z", request: 4 }),
    );

    const button = screen.getByRole("button", { name: "Download" });
    expect(button).toHaveAccessibleDescription("Access until 30 Nov 2026");
    await expectNoBlockingA11yViolations(container);
  });

  it("tells the reader why when the route refuses, and re-reads the state", async () => {
    const refusal = new Blob([JSON.stringify({ detail: "Your download access has expired.", code: "grant_expired" })]);
    downloadCopy.mockRejectedValue({ response: { status: 403, data: refusal } });
    const { onChanged } = renderControl(state({ state: "granted", allowed: true, grant_expires_at: "2026-11-30T08:00:00Z" }));

    await userEvent.click(screen.getByRole("button", { name: "Download" }));

    await waitFor(() =>
      expect(addToast).toHaveBeenCalledWith({ type: "error", message: "Your download access has expired." }),
    );
    expect(onChanged).toHaveBeenCalled();
    expect(downloadBlob).not.toHaveBeenCalled();
  });
});

describe("a reader who must ask", () => {
  it("offers a request, and sends it from the dialog", async () => {
    requestDownload.mockResolvedValue({});
    const { container, onChanged } = renderControl(state({ state: "none" }));
    expect(screen.queryByRole("button", { name: "Download" })).not.toBeInTheDocument();
    await expectNoBlockingA11yViolations(container);

    await userEvent.click(screen.getByRole("button", { name: "Request download" }));
    const dialog = await screen.findByRole("dialog", { name: "Request download access" });
    expect(dialog).toHaveTextContent("A published thesis");

    await userEvent.click(screen.getByRole("button", { name: "Submit request" }));

    await waitFor(() => expect(requestDownload).toHaveBeenCalledWith(7));
    expect(onChanged).toHaveBeenCalled();
  });

  it("shows a pending request and offers nothing to click", () => {
    renderControl(state({ state: "pending", message: "Your download request is waiting for RDCO's decision.", request: 3 }));

    expect(screen.getByText("Request pending")).toBeInTheDocument();
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
  });

  it.each([
    ["declined", "Request declined"],
    ["revoked", "Access revoked"],
    ["expired", "Access expired"],
  ] as const)("names a %s request and offers to request again", async (ended, word) => {
    const { container } = renderControl(state({ state: ended }));

    expect(screen.getByRole("button", { name: "Request again" })).toHaveAccessibleDescription(word);
    expect(screen.queryByRole("button", { name: "Download" })).not.toBeInTheDocument();
    await expectNoBlockingA11yViolations(container);
  });
});

it("shows nothing when the server says nothing", () => {
  const { container } = renderControl(null);
  expect(container).toBeEmptyDOMElement();
});
