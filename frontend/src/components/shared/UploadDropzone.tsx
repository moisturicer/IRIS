/**
 * Drag-and-drop and click-to-browse file upload (IR-405; spec §4.12). It
 * replaces `FileUploadZone`.
 *
 * The parent performs the upload; this component covers everything around it:
 *
 * - **Before:** with `validate`, a file whose type is not in `accept`, or
 *   whose size is over `maxBytes`, is refused here, before anything is sent,
 *   and the message names the limit. Without `validate` nothing is checked,
 *   which is how `FileUploadZone` behaved and what its two callers still rely
 *   on: they validate for themselves.
 * - **During:** pass `upload={{ status: "uploading", fileName, progress }}`.
 *   The zone becomes a progress bar, and cannot be used again until the
 *   upload ends.
 * - **After a failure:** pass `upload={{ status: "failed", fileName, error,
 *   onRetry }}`. The author retries without choosing the file again.
 *
 * One live region stays mounted throughout, so a screen reader hears the
 * upload start and finish. Keyboard focus follows the zone into the progress
 * bar and back, rather than dropping to the page.
 */
import { forwardRef, useEffect, useRef, useState, type DragEvent, type KeyboardEvent } from "react";

import { COLOUR_TRANSITION, FOCUS_RING } from "@/components/ui/interaction";
import { PILL_SECONDARY } from "@/components/ui/pillStyles";
import { cn, formatBytes } from "@/lib/utils";

/** The upload the parent has in hand, if any. */
export type UploadState =
  | { status: "uploading"; fileName: string; progress: number }
  | { status: "failed"; fileName: string; error: string; onRetry: () => void };

interface UploadDropzoneProps {
  onFiles:   (files: File[]) => void;
  /** The zone's accessible name, e.g. "Upload manuscript". */
  label?:    string;
  /** As the file input's `accept`: extensions and MIME types, e.g. ".pdf". */
  accept?:   string;
  multiple?: boolean;
  disabled?: boolean;
  /** Check type against `accept` and size against `maxBytes` before handing files on. */
  validate?: boolean;
  maxBytes?: number;
  /**
   * The accepted-types line under the prompt. With `validate` it defaults to
   * one built from `accept` and `maxBytes`, so it cannot disagree with them.
   */
  hint?:     string;
  upload?:   UploadState | null;
}

function acceptedPatterns(accept: string | undefined): string[] {
  return (accept ?? "")
    .split(",")
    .map((part) => part.trim().toLowerCase())
    .filter(Boolean);
}

/** [".pdf", ".docx"] → "PDF, DOCX"; ["image/*"] → "IMAGE files". */
function describeAccepted(patterns: string[]): string {
  return patterns
    .map((p) => (p.startsWith(".") ? p.slice(1).toUpperCase() : `${p.split("/")[0].toUpperCase()} files`))
    .join(", ");
}

function matchesAccept(file: File, patterns: string[]): boolean {
  if (patterns.length === 0) return true;
  const name = file.name.toLowerCase();
  const type = file.type.toLowerCase();
  return patterns.some((pattern) => {
    if (pattern.startsWith(".")) return name.endsWith(pattern);
    if (pattern.endsWith("/*")) return type.startsWith(pattern.slice(0, -1));
    return type === pattern;
  });
}

/** The first reason any file must be refused, or null when all may go. */
function refusal(files: File[], patterns: string[], maxBytes: number | undefined): string | null {
  for (const file of files) {
    if (!matchesAccept(file, patterns)) {
      return `${file.name} is not an accepted file. Accepted: ${describeAccepted(patterns)}.`;
    }
    if (maxBytes != null && file.size > maxBytes) {
      return `${file.name} is ${formatBytes(file.size)}. The limit is ${formatBytes(maxBytes)}.`;
    }
  }
  return null;
}

function defaultHint(patterns: string[], maxBytes: number | undefined): string | undefined {
  const parts = [
    patterns.length > 0 ? describeAccepted(patterns) : null,
    maxBytes != null ? `up to ${formatBytes(maxBytes)}` : null,
  ].filter(Boolean);
  return parts.length > 0 ? parts.join(", ") : undefined;
}

export function UploadDropzone({
  onFiles,
  label,
  accept,
  multiple = false,
  disabled = false,
  validate = false,
  maxBytes,
  hint,
  upload,
}: UploadDropzoneProps) {
  const [dragging, setDragging] = useState(false);
  const [refused, setRefused] = useState<string | null>(null);
  const [announcement, setAnnouncement] = useState("");
  const inputRef = useRef<HTMLInputElement>(null);
  const zoneRef = useRef<HTMLDivElement>(null);
  const progressRef = useRef<HTMLDivElement>(null);
  const hadFocus = useRef(false);
  // Starts empty, so an upload already under way when the zone mounts is announced too.
  const previous = useRef<UploadState | null | undefined>(null);

  const patterns = acceptedPatterns(accept);
  const uploading = upload?.status === "uploading";

  // Read during render, while the element about to be swapped out is still in
  // the page: once it is removed, focus has already fallen to <body>.
  if (uploading !== (previous.current?.status === "uploading")) {
    const active = typeof document === "undefined" ? null : document.activeElement;
    hadFocus.current = active != null && (active === zoneRef.current || active === progressRef.current);
  }
  const shownHint = hint ?? (validate ? defaultHint(patterns, maxBytes) : undefined);

  // Announce the start and the end of an upload, and carry keyboard focus
  // across the swap between the zone and the progress bar.
  useEffect(() => {
    const before = previous.current;
    previous.current = upload;
    if (upload?.status === "uploading" && before?.status !== "uploading") {
      setAnnouncement(`Uploading ${upload.fileName}`);
      if (hadFocus.current) progressRef.current?.focus();
    } else if (before?.status === "uploading" && upload?.status !== "uploading") {
      // A failure is announced by its own alert; only success needs saying here.
      setAnnouncement(upload ? "" : `${before.fileName} uploaded`);
      if (hadFocus.current) zoneRef.current?.focus();
    }
  }, [upload]);

  function take(files: File[]) {
    if (disabled || files.length === 0) return;
    const reason = validate ? refusal(files, patterns, maxBytes) : null;
    setRefused(reason);
    if (!reason) onFiles(files);
  }

  function browse() {
    if (!disabled) inputRef.current?.click();
  }

  function handleKeyDown(e: KeyboardEvent<HTMLDivElement>) {
    // A div with role="button" gets neither key for free; both are expected.
    if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      browse();
    }
  }

  function handleDrop(e: DragEvent<HTMLDivElement>) {
    e.preventDefault();
    setDragging(false);
    take(Array.from(e.dataTransfer.files));
  }

  const failure =
    upload?.status === "failed"
      ? `${upload.fileName} could not be uploaded. ${upload.error}`
      : refused;

  return (
    <div>
      <span role="status" className="sr-only">
        {announcement}
      </span>

      {uploading ? (
        <ProgressPanel
          ref={progressRef}
          fileName={upload.fileName}
          progress={upload.progress}
        />
      ) : (
        <div
          ref={zoneRef}
          role="button"
          aria-label={label}
          aria-disabled={disabled || undefined}
          tabIndex={disabled ? -1 : 0}
          onClick={(e) => {
            // The hidden input's own click bubbles up to here; reopening the
            // chooser from it would open it twice.
            if (e.target !== inputRef.current) browse();
          }}
          onKeyDown={handleKeyDown}
          onDragOver={(e) => {
            e.preventDefault();
            if (!disabled) setDragging(true);
          }}
          onDragLeave={() => setDragging(false)}
          onDrop={handleDrop}
          className={cn(
            "flex flex-col items-center justify-center gap-2 rounded-xl border-2 border-dashed px-6 py-10 select-none",
            COLOUR_TRANSITION,
            FOCUS_RING,
            dragging ? "border-brand bg-brand-50" : "border-stone-300 bg-stone-50",
            disabled ? "opacity-50 cursor-not-allowed" : "cursor-pointer hover:border-stone-500",
          )}
        >
          <i className="fas fa-cloud-arrow-up text-3xl text-stone-500" aria-hidden="true" />
          <p className="text-body text-stone-700 font-medium">
            Drag and drop here, or <span className="text-brand underline underline-offset-2">browse</span>
          </p>
          {shownHint && <p className="text-small text-stone-600">{shownHint}</p>}
          <input
            ref={inputRef}
            type="file"
            accept={accept}
            multiple={multiple}
            // The attribute, not Tailwind's class: the zone is the control, and the
            // input must stay out of the accessibility tree wherever styles are absent.
            hidden
            disabled={disabled}
            onChange={(e) => {
              take(Array.from(e.target.files ?? []));
              // Reset so the same file can be chosen again after a refusal.
              e.target.value = "";
            }}
          />
        </div>
      )}

      {failure && (
        <div role="alert" className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-small text-brand">
          <span className="flex items-start gap-1.5">
            <i className="fas fa-circle-exclamation mt-1" aria-hidden="true" />
            <span>{failure}</span>
          </span>
          {upload?.status === "failed" && (
            <button
              type="button"
              onClick={upload.onRetry}
              aria-label="Retry upload"
              className={cn(PILL_SECONDARY, FOCUS_RING)}
            >
              <i className="fas fa-rotate-right" aria-hidden="true" />
              Retry
            </button>
          )}
        </div>
      )}
    </div>
  );
}

interface ProgressPanelProps {
  fileName: string;
  progress: number;
}

/** Focusable (programmatically only) so keyboard focus has somewhere to land. */
const ProgressPanel = forwardRef<HTMLDivElement, ProgressPanelProps>(function ProgressPanel(
  { fileName, progress },
  ref,
) {
  const percent = Math.min(100, Math.max(0, Math.round(progress)));
  const name = `Uploading ${fileName}`;
  return (
    <div
      ref={ref}
      role="group"
      aria-label="Upload in progress"
      tabIndex={-1}
      className={cn("rounded-xl border border-stone-200 bg-white px-5 py-4", FOCUS_RING)}
    >
      <div className="flex items-center justify-between gap-3 text-small" aria-hidden="true">
        <span className="font-medium text-stone-800 truncate">{name}</span>
        <span className="text-stone-600 tabular-nums">{percent}%</span>
      </div>
      <div
        role="progressbar"
        aria-label={name}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={percent}
        className="mt-2 h-1.5 rounded-full bg-stone-100 overflow-hidden"
      >
        {/* Moved by transform, not width (01-design-system §0, motion). */}
        <div
          className="h-full w-full origin-left rounded-full bg-brand transition-transform duration-200 motion-reduce:transition-none"
          style={{ transform: `scaleX(${percent / 100})` }}
        />
      </div>
    </div>
  );
});
