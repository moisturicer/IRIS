import { forwardRef, useCallback, useEffect, useId, useRef, useState } from "react";

import { documentsApi } from "@/api/documents";
import { recordsApi } from "@/api/records";
import { ProgressBar, toPercent } from "@/components/shared/ProgressBar";
import { COLOUR_TRANSITION, FOCUS_RING } from "@/components/ui/interaction";
import { PILL_SECONDARY } from "@/components/ui/pillStyles";
import { cn, formatDate } from "@/lib/utils";
import { errorDetail } from "@/lib/errorDetail";
import { ItemStatusChip } from "./itemStatus";
import type { DocumentRequest, DocumentRequestItem } from "@/types/records";

interface ActionRequiredPanelProps {
  recordId: number;
  /** The panel's id, so a link can land on it (IR-625). */
  id?: string;
  /** Told after an upload, so the page can refresh what it derived from the old state. */
  onChanged?: () => void;
}

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
 * An item's upload stays a compact button (spec §4.10 as amended
 * 2026-10-06), not an `UploadDropzone`, yet behaves like one (IR-471): a
 * progress bar while it runs, Retry with the same file after a failure, and
 * a live region per row that announces each start and finish.
 *
 * Each item reads in spec §4.10's one vocabulary (`itemStatus`): Requested,
 * Uploaded · awaiting review, Accepted, Replacement needed.
 *
 * An upload the requesting party rejected is back to missing, with the
 * reviewer's reason beside it and the upload control offered again (ADR-022
 * §3.4). A list that fails to load says so: an empty panel would read as
 * "nothing required", which is exactly the wrong thing to tell an owner. A
 * refresh that fails after an upload keeps the list on screen and says so
 * inside the panel, so another item's upload in progress is not lost (IR-471).
 */
export function ActionRequiredPanel({ recordId, id, onChanged }: ActionRequiredPanelProps) {
  const headingId = useId();
  const [requests, setRequests] = useState<DocumentRequest[] | null>(null);
  const [failed, setFailed] = useState<string | null>(null);
  /** A refresh that failed after a list was shown: reported inside the panel, never instead of it. */
  const [refreshFailed, setRefreshFailed] = useState<string | null>(null);
  const hasList = useRef(false);
  /** Ids of requests seen open since this panel mounted. */
  const seenOpen = useRef<Set<number>>(new Set());

  const load = useCallback(
    () =>
      recordsApi
        .documentRequests(recordId)
        .then(({ data }) => {
          data.filter((r) => r.state === "open").forEach((r) => seenOpen.current.add(r.id));
          hasList.current = true;
          setRequests(data);
          setFailed(null);
          setRefreshFailed(null);
        })
        .catch((error: unknown) => {
          // Before any list arrives, the panel has nothing to show but the failure.
          if (!hasList.current) {
            setFailed(errorDetail(error, "Could not load the documents reviewers asked for. Reload the page to try again."));
            return;
          }
          // After one has, keep it, so an upload still running in another row stays in view.
          setRefreshFailed(errorDetail(error, "Could not refresh the documents reviewers asked for. Reload the page to see the latest."));
        }),
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
        {failed}
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
      id={id}
      tabIndex={id ? -1 : undefined}
      aria-labelledby={headingId}
      className="rounded-2xl border border-brand-200 bg-brand-50 p-4 space-y-4 scroll-mt-20 focus:outline-none"
    >
      <h2 id={headingId} className="text-sm font-bold text-brand-dark flex items-center gap-2">
        <i className="fas fa-file-circle-exclamation text-xs" aria-hidden />
        {anyOpen ? "Action required" : "Requested documents"}
      </h2>
      {refreshFailed && (
        <p role="alert" className="text-xs text-brand-dark">
          {refreshFailed}
        </p>
      )}
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

/** One row's upload, if any: under way, or failed and holding the file for Retry. */
type RowUpload =
  | { status: "uploading"; fileName: string; progress: number }
  | { status: "failed"; file: File; error: string };

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
  const [upload, setUpload] = useState<RowUpload | null>(null);
  /**
   * This row's live region. One per row, as UploadDropzone has one per zone,
   * so two items uploading at once never overwrite each other's news.
   */
  const [announcement, setAnnouncement] = useState("");
  /** Set synchronously, so a second click before the re-render cannot send twice. */
  const inFlight = useRef(false);
  const uploading = upload?.status === "uploading";

  const rowRef = useRef<HTMLLIElement>(null);
  const progressRef = useRef<HTMLSpanElement>(null);
  const retryRef = useRef<HTMLButtonElement>(null);
  /** Whether keyboard focus was in this row when the upload control was swapped out. */
  const carryFocus = useRef(false);

  const send = async (file: File) => {
    if (inFlight.current) return;
    inFlight.current = true;
    const active = typeof document === "undefined" ? null : document.activeElement;
    carryFocus.current = active != null && (rowRef.current?.contains(active) ?? false);
    setUpload({ status: "uploading", fileName: file.name, progress: 0 });
    setAnnouncement(`Uploading ${file.name}`);
    try {
      await documentsApi.uploadForRequestItem(recordId, item.id, file, {
        onProgress: (progress) =>
          setUpload((u) => (u?.status === "uploading" ? { ...u, progress } : u)),
      });
    } catch (err) {
      inFlight.current = false;
      // The failure is announced by its own alert; saying it here too would say it twice.
      setAnnouncement("");
      setUpload({
        status: "failed",
        file,
        error: errorDetail(err, "The upload failed. Please try again."),
      });
      return;
    }
    inFlight.current = false;
    setUpload(null);
    setAnnouncement(`${file.name} uploaded`);
    // Outside the try: the file is already sent, so a failed refresh must never offer Retry.
    await onUploaded();
  };

  // Carry keyboard focus across each swap, as UploadDropzone does, instead of
  // letting it fall to the page when the focused control leaves it.
  const status = upload?.status;
  useEffect(() => {
    if (!carryFocus.current) return;
    if (status === "uploading") progressRef.current?.focus();
    else if (status === "failed") retryRef.current?.focus();
    else {
      rowRef.current?.focus();
      carryFocus.current = false;
    }
  }, [status]);

  const onFile = (file: File | undefined) => {
    if (file) void send(file);
  };

  return (
    <li ref={rowRef} tabIndex={-1} className="py-2 first:pt-0 last:pb-0 focus:outline-none">
      {/* Mounted with the row, so the first announcement is heard. */}
      <span role="status" className="sr-only">
        {announcement}
      </span>
      <div className="flex items-center justify-between gap-3 flex-wrap">
        <span className="text-sm font-semibold text-stone-800 min-w-0 break-words">
          {item.label}
        </span>
        <span className="flex items-center gap-2">
          <ItemStatusChip item={item} />
          {item.state === "missing" && uploading && (
            <CompactProgress
              ref={progressRef}
              fileName={upload.fileName}
              progress={upload.progress}
            />
          )}
          {item.state === "missing" && !uploading && (
            <label
              htmlFor={inputId}
              className={cn(
                "inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg bg-brand text-white text-xs font-bold cursor-pointer hover:bg-brand-light",
                COLOUR_TRANSITION,
                // FOCUS_RING's ring, on the label: the focused element is its hidden input.
                "has-[:focus-visible]:ring-2 has-[:focus-visible]:ring-brand has-[:focus-visible]:ring-offset-2",
              )}
            >
              <i className="fas fa-upload text-2xs" aria-hidden />
              Upload
              <span className="sr-only"> {item.label}</span>
              <input
                id={inputId}
                type="file"
                accept="application/pdf,.pdf"
                className="sr-only"
                onChange={(e) => {
                  onFile(e.target.files?.[0]);
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
      {upload?.status === "failed" && (
        <div role="alert" className="mt-1 flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-brand">
          <span className="break-words min-w-0">
            {upload.file.name} could not be uploaded. {upload.error}
          </span>
          <button
            ref={retryRef}
            type="button"
            onClick={() => void send(upload.file)}
            aria-label={`Retry uploading ${upload.file.name}`}
            className={cn(PILL_SECONDARY, FOCUS_RING)}
          >
            <i className="fas fa-rotate-right text-2xs" aria-hidden />
            Retry
          </button>
        </div>
      )}
    </li>
  );
}

/**
 * The row's progress, as compact as the button it replaces (spec §4.10 as
 * amended 2026-10-06): a short bar and a percentage, not `UploadDropzone`'s panel.
 */
const CompactProgress = forwardRef<HTMLSpanElement, { fileName: string; progress: number }>(
  function CompactProgress({ fileName, progress }, ref) {
    return (
      <span className="inline-flex items-center gap-2">
        <ProgressBar
          ref={ref}
          focusable
          label={`Uploading ${fileName}`}
          progress={progress}
          className={cn("h-1.5 w-20 bg-brand-100", FOCUS_RING)}
        />
        <span className="text-2xs font-semibold text-stone-600 tabular-nums" aria-hidden>
          {toPercent(progress)}%
        </span>
      </span>
    );
  },
);
