import { useCallback, useEffect, useId, useState } from "react";

import { recordsApi } from "@/api/records";
import { cn, formatDate } from "@/lib/utils";
import { useIsReviewer } from "@/store/auth.store";
import type {
  DocumentRequest,
  DocumentRequestItem,
  DocumentRequestItemState,
  RecordDetail,
} from "@/types/records";

import { errorDetail } from "./errorDetail";
import { RequestDocumentDialog } from "./RequestDocumentDialog";

interface ReviewerDocumentRequestsProps {
  record: Pick<RecordDetail, "id" | "can_request_document" | "current_holders">;
  /** Told after a request is made, decided or withdrawn, so the page can re-read. */
  onChanged?: () => void;
  /** Placement on the host page; applied only when there is something to show. */
  className?: string;
}

/** Presentation only; every word comes from the server. */
const ITEM_TONE: Record<DocumentRequestItemState, string> = {
  missing:  "text-amber-800 bg-amber-100",
  uploaded: "text-sky-800 bg-sky-100",
  accepted: "text-emerald-800 bg-emerald-100",
  rejected: "text-red-800 bg-red-100",
};

/** A request still asks something of the party that made it. */
function needsTheRequester(r: DocumentRequest): boolean {
  if (!r.can_manage || r.state === "withdrawn") return false;
  return r.state === "open" || r.items.some((i) => i.state === "uploaded");
}

/**
 * The reviewer's side of document requests, shared by the reviewer page and the
 * paper view (IR-262, IR-263; ADR-022 §3.4, §4).
 *
 * Two parts. **Request documents**, when the API names a party the viewer may
 * ask as (`can_request_document`). And the requests the viewer's party made
 * that still need it: Accept or Reject on each uploaded item -- a rejection
 * needs a reason, which the owner reads -- and Withdraw on an open request.
 * Who may manage a request is the server's `can_manage`, never decided here.
 *
 * Requests are loaded only for a reviewing role. For anyone else the list
 * endpoint would refuse, and a 403 here -- a reviewer who took no part in the
 * record (IR-349) -- just means there is nothing to manage.
 */
export function ReviewerDocumentRequests({
  record,
  onChanged,
  className,
}: ReviewerDocumentRequestsProps) {
  const isReviewer = useIsReviewer();
  const headingId = useId();
  const [requests, setRequests] = useState<DocumentRequest[]>([]);
  const [requesting, setRequesting] = useState(false);
  const [requested, setRequested] = useState(false);

  const load = useCallback(() => {
    if (!isReviewer) return Promise.resolve();
    return recordsApi
      .documentRequests(record.id)
      .then(({ data }) => setRequests(data))
      .catch(() => setRequests([]));
  }, [isReviewer, record.id]);

  useEffect(() => {
    void load();
  }, [load]);

  const changed = async () => {
    await load();
    onChanged?.();
  };

  const mine = requests.filter(needsTheRequester);
  const canRequest = record.can_request_document.length > 0;
  if (!canRequest && mine.length === 0) return null;

  return (
    <div className={cn("space-y-3", className)}>
      {canRequest && (
        <div>
          <p className="text-[12px] text-stone-600">
            Only missing a file? Ask for it without sending the record back.
          </p>
          <button
            type="button"
            onClick={() => {
              setRequested(false);
              setRequesting(true);
            }}
            className="mt-2 inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-stone-200 bg-white text-[12px] font-bold text-stone-700 hover:border-brand/40 transition-colors"
          >
            <i className="fas fa-file-circle-plus text-[11px]" aria-hidden />
            Request documents
          </button>
          {requested && (
            <p role="status" className="mt-2 text-[12px] text-emerald-700">
              Documents requested. The owner has been notified.
            </p>
          )}
        </div>
      )}

      {mine.length > 0 && (
        <section aria-labelledby={headingId} className="space-y-2">
          <h2 id={headingId} className="text-[11px] font-bold uppercase tracking-wider text-stone-500">
            Documents you requested
          </h2>
          {mine.map((r) => (
            <ManagedRequest key={r.id} request={r} onChanged={changed} />
          ))}
        </section>
      )}

      {requesting && (
        <RequestDocumentDialog
          recordId={record.id}
          parties={record.can_request_document}
          partyLabels={Object.fromEntries(
            record.current_holders.map((h) => [h.party, h.label]),
          )}
          onClose={() => setRequesting(false)}
          onCreated={() => {
            setRequesting(false);
            setRequested(true);
            void changed();
          }}
        />
      )}
    </div>
  );
}

function ManagedRequest({
  request,
  onChanged,
}: {
  request: DocumentRequest;
  onChanged: () => Promise<void>;
}) {
  const listId = useId();
  return (
    <article className="bg-white border border-stone-200 rounded-xl p-3.5">
      <p className="text-[11px] text-stone-500">
        {request.label} · {request.state_label} · {formatDate(request.created_at, "MMM d")}
      </p>
      {/* A text node, never innerHTML (ADR-022 §Security). */}
      <p className="text-[13px] text-stone-700 leading-relaxed mt-1 whitespace-pre-line break-words">
        {request.message}
      </p>
      <p id={listId} className="sr-only">
        Documents in this request
      </p>
      <ul aria-labelledby={listId} className="mt-2 divide-y divide-stone-100">
        {request.items.map((item) => (
          <ManagedItem key={item.id} item={item} onChanged={onChanged} />
        ))}
      </ul>
      {request.state === "open" && <Withdraw request={request} onChanged={onChanged} />}
    </article>
  );
}

function ManagedItem({
  item,
  onChanged,
}: {
  item: DocumentRequestItem;
  onChanged: () => Promise<void>;
}) {
  const reasonId = useId();
  const [rejecting, setRejecting] = useState(false);
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const decide = async (body: Parameters<typeof recordsApi.decideDocumentRequestItem>[1]) => {
    setError(null);
    setBusy(true);
    try {
      await recordsApi.decideDocumentRequestItem(item.id, body);
      setRejecting(false);
      setReason("");
      await onChanged();
    } catch (err) {
      setError(errorDetail(err, "That did not go through. Please try again."));
    } finally {
      setBusy(false);
    }
  };

  const decidable = item.state === "uploaded";

  return (
    <li className="py-2 first:pt-0 last:pb-0">
      <div className="flex items-center justify-between gap-3 flex-wrap">
        <span className="text-[13px] font-semibold text-stone-800 min-w-0 break-words">
          {item.label}
        </span>
        <span className="flex items-center gap-1.5 flex-wrap">
          <span className={cn("px-1.5 py-0.5 rounded text-[11px] font-bold", ITEM_TONE[item.state])}>
            {item.state_label}
          </span>
          {decidable && (
            <>
              <button
                type="button"
                disabled={busy}
                aria-label={`Accept ${item.label}`}
                onClick={() => void decide({ action: "accept" })}
                className="px-2 py-1 rounded-lg bg-emerald-700 text-white text-[12px] font-bold hover:bg-emerald-800 disabled:opacity-60"
              >
                Accept
              </button>
              <button
                type="button"
                disabled={busy}
                aria-label={`Reject ${item.label}`}
                aria-expanded={rejecting}
                onClick={() => setRejecting((v) => !v)}
                className="px-2 py-1 rounded-lg border border-red-200 text-[12px] font-bold text-red-700 hover:bg-red-50 disabled:opacity-60"
              >
                Reject
              </button>
            </>
          )}
        </span>
      </div>

      {item.state === "missing" && item.rejection_reason && (
        <p className="text-[12px] text-stone-600 mt-1 break-words">
          You rejected the last upload: “{item.rejection_reason}”
        </p>
      )}

      {rejecting && (
        <form
          className="mt-2 space-y-2"
          onSubmit={(e) => {
            e.preventDefault();
            if (reason.trim()) void decide({ action: "reject", reason: reason.trim() });
          }}
        >
          <label htmlFor={reasonId} className="block text-[12px] font-semibold text-stone-700">
            Why is {item.label} not acceptable?{" "}
            <span className="font-normal text-stone-500">The owner reads this.</span>
          </label>
          <textarea
            id={reasonId}
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            rows={2}
            className="w-full rounded-lg border border-stone-200 p-2 text-[13px] focus:outline-none focus:border-brand"
          />
          <div className="flex gap-2">
            <button
              type="submit"
              disabled={busy || !reason.trim()}
              className="px-2.5 py-1 rounded-lg bg-red-700 text-white text-[12px] font-bold hover:bg-red-800 disabled:opacity-60"
            >
              Send rejection
            </button>
            <button
              type="button"
              onClick={() => {
                setRejecting(false);
                setReason("");
              }}
              className="px-2.5 py-1 rounded-lg border border-stone-200 text-[12px] font-semibold text-stone-700 hover:bg-stone-50"
            >
              Cancel
            </button>
          </div>
        </form>
      )}

      {error && (
        <p role="alert" className="text-[12px] text-red-700 mt-1">
          {error}
        </p>
      )}
    </li>
  );
}

function Withdraw({
  request,
  onChanged,
}: {
  request: DocumentRequest;
  onChanged: () => Promise<void>;
}) {
  const reasonId = useId();
  const [confirming, setConfirming] = useState(false);
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const withdraw = async () => {
    setError(null);
    setBusy(true);
    try {
      await recordsApi.withdrawDocumentRequest(request.id, reason.trim() || undefined);
      await onChanged();
    } catch (err) {
      setError(errorDetail(err, "Could not withdraw the request. Please try again."));
      setBusy(false);
    }
  };

  if (!confirming) {
    return (
      <button
        type="button"
        onClick={() => setConfirming(true)}
        className="mt-2 text-[12px] font-semibold text-stone-600 underline underline-offset-2 hover:text-stone-900"
      >
        Withdraw request
      </button>
    );
  }

  return (
    <div className="mt-2 pt-2 border-t border-stone-100 space-y-2">
      <p className="text-[12px] text-stone-700">
        The owner will no longer be asked for these documents. The request stays in the history.
      </p>
      <label htmlFor={reasonId} className="block text-[12px] font-semibold text-stone-700">
        Reason <span className="font-normal text-stone-500">(optional)</span>
      </label>
      <textarea
        id={reasonId}
        value={reason}
        onChange={(e) => setReason(e.target.value)}
        rows={2}
        className="w-full rounded-lg border border-stone-200 p-2 text-[13px] focus:outline-none focus:border-brand"
      />
      <div className="flex gap-2">
        <button
          type="button"
          disabled={busy}
          onClick={() => void withdraw()}
          className="px-2.5 py-1 rounded-lg bg-stone-800 text-white text-[12px] font-bold hover:bg-stone-900 disabled:opacity-60"
        >
          Confirm withdrawal
        </button>
        <button
          type="button"
          disabled={busy}
          onClick={() => setConfirming(false)}
          className="px-2.5 py-1 rounded-lg border border-stone-200 text-[12px] font-semibold text-stone-700 hover:bg-stone-50"
        >
          Keep request
        </button>
      </div>
      {error && (
        <p role="alert" className="text-[12px] text-red-700">
          {error}
        </p>
      )}
    </div>
  );
}
