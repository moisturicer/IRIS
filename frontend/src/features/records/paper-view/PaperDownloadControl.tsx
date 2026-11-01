import { useId, useState } from "react";
import { Button } from "@/components/ui";
import { DownloadRequestModal } from "@/components/records/DownloadRequestModal";
import { useCancelDownloadRequest } from "@/components/records/useCancelDownloadRequest";
import { useDownloadCopy } from "@/components/records/useDownloadCopy";
import { cn, formatDate } from "@/lib/utils";
import type { DownloadState } from "@/types/records";
import { CONTROL_SIZE } from "./controls";

export interface PaperDownloadControlProps {
  recordId: number;
  recordTitle: string;
  /** The server's answer (IR-677). Null or absent: nothing to offer. */
  download: DownloadState | null | undefined;
  /** Paper mode's toolbar, where controls carry their words (IR-569). */
  fill?: boolean;
  /** The state may have moved: re-read the record. */
  onChanged?: () => void;
}

/** The word beside a refused state's "Request again" (ADR-048). */
const ENDED_LABEL: Partial<Record<DownloadState["state"], string>> = {
  declined: "Request declined",
  revoked: "Access revoked",
  expired: "Access expired",
};

/**
 * The reader's download control (IR-677, ADR-048). The server says where the
 * viewer stands; this only picks the control for it. Download saves a copy
 * through `/records/<id>/download/`, so every saved copy is marked with who
 * it was made for (IR-676) -- never the bytes the reader already holds.
 */
export function PaperDownloadControl({
  recordId,
  recordTitle,
  download,
  fill = false,
  onChanged,
}: PaperDownloadControlProps) {
  // Refused: the grant ended or was revoked since the page loaded.
  const { saving, download: handleDownload } = useDownloadCopy(onChanged);
  const [asking, setAsking] = useState(false);
  // Cancelled, or decided since the page loaded: either way, re-read.
  const { cancelling, cancel } = useCancelDownloadRequest(onChanged);
  const describedBy = useId();
  const noteId = useId();

  if (!download) return null;

  const note = (text: string) => (
    <span id={describedBy} className="text-xs text-stone-600">
      {text}
    </span>
  );

  if (download.allowed) {
    const until = download.state === "granted" && download.grant_expires_at
      ? `Access until ${formatDate(download.grant_expires_at, "d MMM yyyy")}`
      : null;
    return (
      <span className="inline-flex items-center gap-2">
        {until && note(until)}
        <Button
          variant="ghost"
          size={fill ? "sm" : "icon"}
          onClick={() => void handleDownload(recordId)}
          loading={saving}
          aria-label="Download"
          aria-describedby={until ? describedBy : undefined}
          title={download.message}
          className={cn(fill && "text-stone-600", fill && CONTROL_SIZE)}
        >
          <i className="fas fa-download" aria-hidden />
          {fill && <span aria-hidden className="hidden reading-split:inline">Download</span>}
        </Button>
      </span>
    );
  }

  if (download.state === "pending") {
    const pendingRequest = download.request;
    return (
      <span className="inline-flex items-center gap-2">
        <span className="inline-flex items-center gap-1.5 text-xs font-semibold text-stone-600" title={download.message}>
          <i className="fas fa-clock" aria-hidden />
          Request pending
        </span>
        {pendingRequest != null && (
          <Button
            variant="ghost"
            size="sm"
            onClick={() => void cancel(pendingRequest)}
            loading={cancelling}
            className={cn("text-stone-600", CONTROL_SIZE)}
          >
            Cancel request
          </Button>
        )}
      </span>
    );
  }

  const ended = ENDED_LABEL[download.state];
  // RDCO's reason (IR-688), shown beside Request again (IR-743). Absent on an
  // older API; blank on a decline made before notes existed.
  const endedByRdco = download.state === "declined" || download.state === "revoked";
  const rdcoNote = endedByRdco && download.rdco_note !== undefined
    ? `RDCO's note: ${download.rdco_note.trim() || "No note recorded"}`
    : null;
  const descriptions = [ended && describedBy, rdcoNote && noteId].filter(Boolean).join(" ");
  return (
    <span className="inline-flex items-center gap-2">
      {ended && note(ended)}
      {rdcoNote && (
        <span id={noteId} className="max-w-xs text-xs text-stone-600 line-clamp-2" title={rdcoNote}>
          {rdcoNote}
        </span>
      )}
      <Button
        variant="outline"
        size="sm"
        onClick={() => setAsking(true)}
        aria-describedby={descriptions || undefined}
        title={download.message}
        className={CONTROL_SIZE}
      >
        <i className="fas fa-download" aria-hidden />
        {ended ? "Request again" : "Request download"}
      </Button>
      <DownloadRequestModal
        open={asking}
        onClose={() => setAsking(false)}
        recordId={recordId}
        recordTitle={recordTitle}
        onSubmitted={onChanged}
      />
    </span>
  );
}
