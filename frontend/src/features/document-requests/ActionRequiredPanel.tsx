import { useCallback, useEffect, useId, useRef, useState } from "react";

import { documentsApi } from "@/api/documents";
import { recordsApi } from "@/api/records";
import { cn, formatDate } from "@/lib/utils";
import { errorDetail } from "./errorDetail";
import type { DocumentRequest, DocumentRequestItem, DocumentRequestItemState } from "@/types/records";

interface ActionRequiredPanelProps {
  recordId: number;
  /** Told after an upload, so the page can refresh what it derived from the old state. */
  onChanged?: () => void;
}

/** Presentation only; every word comes from the server. */
const ITEM_TONE: Record<DocumentRequestItemState, string> = {
  missing:  "text-brand bg-brand-100",
  uploaded: "text-stone-900 bg-stone-100",
  accepted: "text-stone-900 bg-stone-100",
  rejected: "text-brand bg-brand-100",
};

/**
 * The owner's list of what reviewers have asked them to provide (IR-262,
 * ADR-022 §3, workflow_routing_architecture.md §9.3).
 *
 * One entry per **open** document request: who asked, why -- in their words,
 * rendered as text -- and an upload control on each item still missing. An
 * upload goes through the ordinary documents endpoint with the item's id, so
 * the file lands in the right slot and the request fulfils itself when the
 * last item arrives. Renders nothing while no request is open.
 *
 * A request the owner fulfils **during this visit** stays on screen, marked
 * fulfilled, so the last upload visibly lands somewhere instead of the whole
 * entry vanishing. On the next visit it is gone from here and lives on in the
 * tracker's document-request history. A withdrawn request is never shown: the
 * reviewer no longer needs it (IR-263).
 *
 * An upload the requesting party rejected is back to missing, with the
 * reviewer's reason beside it and the upload control offered again (ADR-022
 * §3.4). A list that fails to load says so: an empty panel would read as
 * "nothing required", which is exactly the wrong thing to tell an owner.
 */
export function ActionRequiredPanel({ recordId, onChanged }: ActionRequiredPanelProps) {
  const headingId = useId();
  const [requests, setRequests] = useState<DocumentRequest[] | null>(null);
  const [failed, setFailed] = useState(false);
  /** Ids of requests seen open since this panel mounted. */
  const seenOpen = useRef<Set<number>>(new Set());

  const load = useCallback(
    () =>
      recordsApi
        .documentRequests(recordId)
        .then(({ data }) => {
          data.filter((r) => r.state === "open").forEach((r) => seenOpen.current.add(r.id));
          setRequests(data);
          setFailed(false);
        })
        .catch(() => setFailed(true)),
    [recordId],
  );

  useEffect(() => {
    void load();
  }, [load]);

  if (failed) {
    return (
      <p
        role="alert"
        className="rounded-2xl border border-brand-200 bg-brand-50 p-4 text-sm text-brand-dark"
      >
        Could not load the documents reviewers asked for. Reload the page to try again.
      </p>
    );
  }

  const shown = (requests ?? []).filter(
    (r) => r.state === "open" || (r.state === "fulfilled" && seenOpen.current.has(r.id)),
  );
  if (shown.length === 0) return null;
  const anyOpen = shown.some((r) => r.state === "open");

  const uploaded = async () => {
    await load();
    onChanged?.();
  };

  return (
    <section
      aria-labelledby={headingId}
      className="rounded-2xl border border-brand-200 bg-brand-50 p-4 space-y-4"
    >
      <h2 id={headingId} className="text-sm font-bold text-brand-dark flex items-center gap-2">
        <i className="fas fa-file-circle-exclamation text-xs" aria-hidden />
        {anyOpen ? "Action required" : "Requested documents"}
      </h2>
      {shown.map((r) => (
        <RequestEntry key={r.id} recordId={recordId} request={r} onUploaded={uploaded} />
      ))}
    </section>
  );
}

function RequestEntry({
  recordId,
  request,
  onUploaded,
}: {
  recordId: number;
  request: DocumentRequest;
  onUploaded: () => Promise<void>;
}) {
  const listId = useId();
  return (
    <article className="bg-white border border-brand-200 rounded-xl p-3.5">
      <h3 className="text-sm font-bold text-stone-900">
        {request.label} requested documents
      </h3>
      <p className="text-2xs text-stone-500 mt-0.5">
        {request.requested_by && `${request.requested_by} · `}
        {formatDate(request.created_at, "MMM d")}
      </p>
      {request.state === "fulfilled" && (
        <p className="mt-2 text-xs font-semibold text-stone-900 flex items-center gap-1.5">
          <i className="fas fa-circle-check text-2xs" aria-hidden />
          {request.state_label} — {request.label} has been told everything is uploaded.
        </p>
      )}
      {/* A text node, never innerHTML: the reviewer's words, exactly (ADR-022 §Security). */}
      <p className="text-sm text-stone-700 leading-relaxed mt-2 whitespace-pre-line break-words">
        {request.message}
      </p>
      <p id={listId} className="sr-only">
        Documents requested by {request.label}
      </p>
      <ul aria-labelledby={listId} className="mt-3 divide-y divide-stone-100">
        {request.items.map((item) => (
          <ItemRow
            key={item.id}
            recordId={recordId}
            item={item}
            asker={request.label}
            onUploaded={onUploaded}
          />
        ))}
      </ul>
    </article>
  );
}

function ItemRow({
  recordId,
  item,
  asker,
  onUploaded,
}: {
  recordId: number;
  item: DocumentRequestItem;
  /** Who asked, as the server words it. */
  asker: string;
  onUploaded: () => Promise<void>;
}) {
  const inputId = useId();
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const onFile = async (file: File | undefined) => {
    if (!file) return;
    setError(null);
    setUploading(true);
    try {
      await documentsApi.uploadForRequestItem(recordId, item.id, file);
      await onUploaded();
    } catch (err) {
      setError(errorDetail(err, "The upload failed. Please try again."));
    } finally {
      setUploading(false);
    }
  };

  return (
    <li className="py-2 first:pt-0 last:pb-0">
      <div className="flex items-center justify-between gap-3 flex-wrap">
        <span className="text-sm font-semibold text-stone-800 min-w-0 break-words">
          {item.label}
        </span>
        <span className="flex items-center gap-2">
          <span
            className={cn("px-1.5 py-0.5 rounded text-2xs font-bold", ITEM_TONE[item.state])}
          >
            {item.state_label}
          </span>
          {item.state === "missing" && (
            <label
              htmlFor={inputId}
              className={cn(
                "inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg bg-brand text-white text-xs font-bold cursor-pointer hover:bg-brand-light focus-within:ring-2 focus-within:ring-brand/40",
                uploading && "opacity-60 pointer-events-none",
              )}
            >
              <i className="fas fa-upload text-2xs" aria-hidden />
              {uploading ? "Uploading…" : "Upload"}
              <span className="sr-only"> {item.label}</span>
              <input
                id={inputId}
                type="file"
                accept="application/pdf,.pdf"
                className="sr-only"
                disabled={uploading}
                onChange={(e) => {
                  void onFile(e.target.files?.[0]);
                  e.target.value = "";
                }}
              />
            </label>
          )}
        </span>
      </div>
      {item.state === "missing" && item.rejection_reason && (
        <p className="text-xs text-brand mt-1 break-words">
          {asker} did not accept your last upload: “{item.rejection_reason}”
        </p>
      )}
      {error && (
        <p role="alert" className="text-xs text-brand mt-1">
          {error}
        </p>
      )}
    </li>
  );
}
