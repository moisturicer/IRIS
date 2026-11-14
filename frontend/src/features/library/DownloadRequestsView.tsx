import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";

import { recordsApi } from "@/api/records";
import { DownloadRequestModal } from "@/components/records/DownloadRequestModal";
import { useCancelDownloadRequest } from "@/components/records/useCancelDownloadRequest";
import { useDownloadCopy } from "@/components/records/useDownloadCopy";
import { EmptyState } from "@/components/shared/EmptyState";
import { ReadFailedState } from "@/components/shared/ReadFailedState";
import { isRequestTimeout } from "@/api/requestPolicy";
import { FOCUS_RING } from "@/components/ui/interaction";
import { PILL_SECONDARY } from "@/components/ui/pillStyles";
import { cn, formatDate } from "@/lib/utils";
import type { ReaderDownloadRequest } from "@/types/records";

const DATE = "d MMM yyyy";

/** The state's words and tone. Granted names its end date. */
function stateLabel(request: ReaderDownloadRequest): { text: string; tone: string } {
  switch (request.state) {
    case "pending":
      return { text: "Pending", tone: "border-stone-300 bg-white text-stone-700" };
    case "granted":
      return {
        text: request.grant_expires_at ? `Granted until ${formatDate(request.grant_expires_at, DATE)}` : "Granted",
        tone: "border-stone-300 bg-surface text-brand",
      };
    case "declined":
      return { text: "Declined", tone: "border-stone-300 bg-stone-100 text-stone-900" };
    case "revoked":
      return { text: "Revoked", tone: "border-stone-300 bg-stone-100 text-stone-900" };
    case "expired":
      return { text: "Expired", tone: "border-stone-200 bg-stone-50 text-stone-600" };
  }
}

const ACTION = cn(PILL_SECONDARY, FOCUS_RING, "min-h-9 px-3 text-small");

interface RowProps {
  request: ReaderDownloadRequest;
  onCancel: (id: number) => void;
  onDownload: (recordId: number) => void;
  onRequestAgain: (request: ReaderDownloadRequest) => void;
  busy: boolean;
}

function RequestRow({ request, onCancel, onDownload, onRequestAgain, busy }: RowProps) {
  const label = stateLabel(request);
  const endedByRdco = request.state === "declined" || request.state === "revoked";
  return (
    <li className="flex flex-col gap-3 p-card-compact md:flex-row md:items-start md:justify-between md:p-card">
      <div className="min-w-0 space-y-1">
        <Link
          to={`/records/${request.record}`}
          className={cn("font-display text-body font-semibold text-stone-900 hover:text-brand", FOCUS_RING)}
        >
          {request.record_title}
        </Link>
        <p className="text-label text-stone-500">Asked {formatDate(request.created_at, DATE)}</p>
        {request.note && <p className="text-small text-stone-700">{request.note}</p>}
        {endedByRdco && (
          <p className="text-small text-stone-600">
            RDCO's note: {request.rdco_note.trim() || "No note recorded"}
          </p>
        )}
      </div>
      <div className="flex shrink-0 flex-wrap items-center gap-2 md:justify-end">
        <span className={cn("rounded-full border px-2.5 py-0.5 text-label font-semibold", label.tone)}>
          {label.text}
        </span>
        {request.actions.includes("cancel") && (
          <button type="button" className={ACTION} disabled={busy} onClick={() => onCancel(request.id)}>
            Cancel request
          </button>
        )}
        {request.actions.includes("download") && (
          <button type="button" className={ACTION} disabled={busy} onClick={() => onDownload(request.record)}>
            <i className="fas fa-download" aria-hidden />
            Download
          </button>
        )}
        {request.actions.includes("request_again") && (
          <button type="button" className={ACTION} onClick={() => onRequestAgain(request)}>
            Request again
          </button>
        )}
      </div>
    </li>
  );
}

/**
 * My Library's Download requests (IR-743, ADR-048): every request the reader
 * made, newest first, from `/records/download-requests/mine/`. The server
 * says each one's state and what it offers; this only shows them.
 */
export function DownloadRequestsView() {
  const [requests, setRequests] = useState<ReaderDownloadRequest[]>([]);
  const [loading, setLoading] = useState(true);
  const [failed, setFailed] = useState(false);
  const [interrupted, setInterrupted] = useState(false);
  const [askingAgain, setAskingAgain] = useState<ReaderDownloadRequest | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setFailed(false);
    setInterrupted(false);
    try {
      const { data } = await recordsApi.myDownloadRequests();
      setRequests(Array.isArray(data) ? data : []);
    } catch (error) {
      setFailed(true);
      setInterrupted(isRequestTimeout(error));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { void load(); }, [load]);

  const reload = () => void load();
  const { cancelling, cancel } = useCancelDownloadRequest(reload);
  const { saving, download } = useDownloadCopy(reload);

  if (loading && requests.length === 0) {
    return (
      <div className="space-y-3" role="status">
        <span className="sr-only">Loading your download requests…</span>
        {[0, 1].map((i) => (
          <div key={i} className="h-24 rounded-2xl border border-stone-200 bg-white motion-safe:animate-pulse" aria-hidden />
        ))}
      </div>
    );
  }

  if (failed) {
    return (
      <ReadFailedState
        interrupted={interrupted}
        what="download requests"
        title="Could not load your download requests"
        message="Nothing was changed. Check your connection and try again."
        onRetry={reload}
      />
    );
  }

  if (requests.length === 0) {
    return (
      <EmptyState
        framed
        icon="fa-file-arrow-down"
        title="No download requests yet"
        message="When you ask RDCO for a copy of a paper, the request and its answer appear here."
      />
    );
  }

  return (
    <div>
      <p className="mb-3 text-small text-stone-600">
        Every copy you download carries your name. RDCO decides each request.
      </p>
      <ul className="divide-y divide-stone-100 overflow-hidden rounded-2xl border border-stone-200 bg-white">
        {requests.map((request) => (
          <RequestRow
            key={request.id}
            request={request}
            busy={cancelling || saving}
            onCancel={(id) => void cancel(id)}
            onDownload={(recordId) => void download(recordId)}
            onRequestAgain={setAskingAgain}
          />
        ))}
      </ul>
      {askingAgain && (
        <DownloadRequestModal
          open
          onClose={() => setAskingAgain(null)}
          recordId={askingAgain.record}
          recordTitle={askingAgain.record_title}
          onSubmitted={reload}
        />
      )}
    </div>
  );
}
