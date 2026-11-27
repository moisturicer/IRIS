import { useCallback, useEffect, useId, useState } from "react";

import { recordsApi } from "@/api/records";
import { cn, formatDate } from "@/lib/utils";
import type {
  DocumentRequest,
  DocumentRequestItem,
  RecordDetail,
} from "@/types/records";

import { errorDetail } from "@/lib/errorDetail";
import { ItemStatusChip } from "./itemStatus";
import { RequestDocumentDialog } from "./RequestDocumentDialog";

interface ReviewerDocumentRequestsProps {
  record: Pick<RecordDetail, "id" | "can_request_document" | "current_holders">;
  /**
   * Whether the viewer takes part in the review, as the capabilities adapter
   * says. Requests are loaded only then: for anyone else the list endpoint
   * would refuse (IR-349).
   */
  reviewing: boolean;
  /** Told after a request is made, decided or withdrawn, so the page can re-read. */
  onChanged?: () => void;
  /** Placement on the host page; applied only when there is something to show. */
  className?: string;
}

/** A request still asks something of the party that made it, or is the viewer's own draft. */
function needsTheRequester(r: DocumentRequest): boolean {
  if (r.state === "draft") return true;
  if (!r.can_manage || r.state === "withdrawn") return false;
  return r.state === "open";
}

/**
 * The reviewer's side of document requests, shared by the reviewer page and the
 * paper view (IR-262, IR-263; ADR-022 §3.4, §4).
 *
 * Two parts. **Request documents**, when the API names a party the viewer may
 * ask as (`can_request_document`). A request waits as the viewer's draft,
 * which only they see, until their *Finish review* sends it with *Request
 * changes* or *Comment only* (ADR-022 Amendment 9, IR-1325); they can remove
 * it until then. And the requests the viewer's party made
 * that are still open, with Withdraw. A sent document is supplied, with no
 * Accept or Reject (ADR-022 Amendment 10, IR-1338): if it is the wrong file,
 * the reviewer asks again with a new request.
 * Who may manage a request is the server's `can_manage`, never decided here.
 *
 * Requests are loaded only for a viewer the caller says is reviewing, which
 * comes from the capabilities adapter, never from a role name (IR-411). A 403
 * here still just means there is nothing to manage.
 */
export function ReviewerDocumentRequests({
  record,
  reviewing,
  onChanged,
  className,
}: ReviewerDocumentRequestsProps) {
  const headingId = useId();
  const [requests, setRequests] = useState<DocumentRequest[]>([]);
  const [requesting, setRequesting] = useState(false);
  const [requested, setRequested] = useState(false);

  const load = useCallback(() => {
    if (!reviewing) return Promise.resolve();
    return recordsApi
      .documentRequests(record.id)
      .then(({ data }) => setRequests(data))
      .catch(() => setRequests([]));
  }, [reviewing, record.id]);

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
          <p className="text-xs text-stone-600">
            Ask for documents here. They go to the authors when you finish your review.
          </p>
          <button
            type="button"
            onClick={() => {
              setRequested(false);
              setRequesting(true);
            }}
            className="mt-2 inline-flex items-center gap-1.5 px-3 py-1.5 rounded-control border border-stone-200 bg-white text-xs font-bold text-stone-700 hover:border-brand/40 transition-colors"
          >
            <i className="fas fa-file-circle-plus text-2xs" aria-hidden />
            Request documents
          </button>
          {requested && (
            <p role="status" className="mt-2 text-xs text-stone-900">
              Added to your review. It is sent when you finish your review with Request changes or Comment only.
            </p>
          )}
        </div>
      )}

      {mine.length > 0 && (
        <section aria-labelledby={headingId} className="space-y-2">
          <h2 id={headingId} className="text-2xs font-bold text-stone-500">
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
    <article className="bg-white border border-stone-200 rounded-card p-3.5">
      <p className="text-2xs text-stone-500">
        {request.state === "draft"
          ? <>{request.label} · Not sent yet · goes with your review</>
          : <>{request.label} · {request.state_label} · {formatDate(request.created_at, "MMM d")}</>}
      </p>
      {/* A text node, never innerHTML (ADR-022 §Security). */}
      <p className="text-justified text-sm text-stone-700 leading-relaxed mt-1 whitespace-pre-line break-words">
        {request.message}
      </p>
      <p id={listId} className="sr-only">
        Documents in this request
      </p>
      <ul aria-labelledby={listId} className="mt-2 divide-y divide-stone-100">
        {request.items.map((item) => (
          <ManagedItem key={item.id} item={item} />
        ))}
      </ul>
      {request.state === "open" && <Withdraw request={request} onChanged={onChanged} />}
      {request.state === "draft" && <RemoveDraft request={request} onChanged={onChanged} />}
    </article>
  );
}

function ManagedItem({ item }: { item: DocumentRequestItem }) {
  return (
    <li className="py-2 first:pt-0 last:pb-0">
      <div className="flex items-center justify-between gap-3 flex-wrap">
        <span className="text-sm font-semibold text-stone-800 min-w-0 break-words">
          {item.label}
        </span>
        <ItemStatusChip item={item} />
      </div>

      {/* A rejection made before IR-1338 stays readable. */}
      {item.state === "missing" && item.rejection_reason && (
        <p className="text-xs text-stone-600 mt-1 break-words">
          You rejected the last upload: “{item.rejection_reason}”
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
  const [confirming, setConfirming] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const withdraw = async () => {
    setError(null);
    setBusy(true);
    try {
      await recordsApi.withdrawDocumentRequest(request.id);
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
        className="mt-2 text-xs font-semibold text-stone-600 underline underline-offset-2 hover:text-stone-900"
      >
        Withdraw request
      </button>
    );
  }

  return (
    <div className="mt-2 pt-2 border-t border-stone-100 space-y-2">
      <p className="text-xs text-stone-700">
        The owner will no longer be asked for these documents. The request stays in the history.
      </p>
      <div className="flex gap-2">
        <button
          type="button"
          disabled={busy}
          onClick={() => void withdraw()}
          className="px-2.5 py-1 rounded-control bg-stone-800 text-white text-xs font-bold hover:bg-stone-900 disabled:opacity-60"
        >
          Confirm withdrawal
        </button>
        <button
          type="button"
          disabled={busy}
          onClick={() => setConfirming(false)}
          className="px-2.5 py-1 rounded-control border border-stone-200 text-xs font-semibold text-stone-700 hover:bg-stone-50"
        >
          Keep request
        </button>
      </div>
      {error && (
        <p role="alert" className="text-xs text-brand">
          {error}
        </p>
      )}
    </div>
  );
}

/** Undo a request not sent yet: nobody was asked, so it just goes (Amendment 9). */
function RemoveDraft({
  request,
  onChanged,
}: {
  request: DocumentRequest;
  onChanged: () => Promise<void>;
}) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const remove = async () => {
    setError(null);
    setBusy(true);
    try {
      await recordsApi.withdrawDocumentRequest(request.id);
      await onChanged();
    } catch (err) {
      setError(errorDetail(err, "Could not remove the request. Please try again."));
      setBusy(false);
    }
  };
  const names = request.items.map((i) => i.label).join(", ");
  return (
    <>
      <button
        type="button"
        disabled={busy}
        aria-label={`Remove request for ${names}`}
        onClick={() => void remove()}
        className="mt-2 text-xs font-semibold text-stone-600 underline underline-offset-2 hover:text-stone-900 disabled:opacity-60"
      >
        Remove
      </button>
      {error && (
        <p role="alert" className="text-xs text-brand">
          {error}
        </p>
      )}
    </>
  );
}
