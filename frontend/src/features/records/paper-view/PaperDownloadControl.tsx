import { useId, useState } from "react";
import { recordsApi } from "@/api/records";
import { Button } from "@/components/ui";
import { DownloadRequestModal } from "@/components/records/DownloadRequestModal";
import { cn, downloadBlob, filenameFromDisposition, formatDate } from "@/lib/utils";
import { useUIStore } from "@/store/ui.store";
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

/** A refused download's reason, read out of the blob axios hands back. */
async function refusalDetail(err: unknown): Promise<{ status?: number; detail?: string }> {
  const response = (err as { response?: { status?: number; data?: unknown } }).response;
  let detail: string | undefined;
  if (response?.data instanceof Blob) {
    try {
      detail = (JSON.parse(await response.data.text()) as { detail?: string }).detail;
    } catch {
      detail = undefined;
    }
  }
  return { status: response?.status, detail };
}

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
  const addToast = useUIStore((s) => s.addToast);
  const [saving, setSaving] = useState(false);
  const [asking, setAsking] = useState(false);
  const describedBy = useId();

  if (!download) return null;

  const note = (text: string) => (
    <span id={describedBy} className="text-xs text-stone-600">
      {text}
    </span>
  );

  const handleDownload = async () => {
    setSaving(true);
    try {
      const response = await recordsApi.downloadCopy(recordId);
      const name =
        filenameFromDisposition(response.headers?.["content-disposition"] as string | undefined)
        ?? `record-${recordId}.pdf`;
      downloadBlob(response.data, name);
    } catch (err) {
      const { status, detail } = await refusalDetail(err);
      addToast({ type: "error", message: detail ?? "The paper could not be downloaded. Please try again." });
      // Refused: the grant ended or was revoked since the page loaded.
      if (status === 403) onChanged?.();
    } finally {
      setSaving(false);
    }
  };

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
          onClick={handleDownload}
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
    return (
      <span className="inline-flex items-center gap-1.5 text-xs font-semibold text-stone-600" title={download.message}>
        <i className="fas fa-clock" aria-hidden />
        Request pending
      </span>
    );
  }

  const ended = ENDED_LABEL[download.state];
  return (
    <span className="inline-flex items-center gap-2">
      {ended && note(ended)}
      <Button
        variant="outline"
        size="sm"
        onClick={() => setAsking(true)}
        aria-describedby={ended ? describedBy : undefined}
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
