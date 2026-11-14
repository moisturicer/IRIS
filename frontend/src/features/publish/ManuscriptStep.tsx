/**
 * Publish, step 1: what this is, and the manuscript itself (spec §4.4).
 *
 * The manuscript is the only document asked for (decision 2). Reviewers ask
 * for anything else later through document requests, so there is no slot
 * checklist here.
 */
import { useEffect, useRef, useState } from "react";

import { UploadDropzone, type UploadState } from "@/components/shared/UploadDropzone";
import { Button } from "@/components/ui/Button";
import { FieldError } from "@/components/ui/FieldError";
import { FOCUS_RING } from "@/components/ui/interaction";
import { cn, formatBytes } from "@/lib/utils";
import type { RecordType } from "@/types/records";
import type { ManuscriptMatch } from "@/api/records";
import { Link } from "react-router-dom";

import { typeKey } from "./draft";
import { SELECTED } from "@/components/ui/highlightRoles";

/** The same limit `SubmitDocumentView` and the serializer enforce (50 MB). */
export const MANUSCRIPT_MAX_BYTES = 50 * 1024 * 1024;

export interface AcceptedManuscript {
  fileName: string | null;
  size: number | null;
}

export type ManuscriptUpload =
  | { status: "idle" }
  | { status: "uploading"; fileName: string; progress: number }
  | { status: "failed"; fileName: string; error: string; accepted: AcceptedManuscript | null }
  | ({ status: "done" } & AcceptedManuscript);

export function acceptedManuscript(upload: ManuscriptUpload): AcceptedManuscript | null {
  if (upload.status === "done") return { fileName: upload.fileName, size: upload.size };
  if (upload.status === "failed") return upload.accepted;
  return null;
}

/** One sentence per type. The types come from the server; only the sentence is copy. */
const TYPE_SENTENCES: Record<string, string> = {
  proposal: "An idea you want your adviser to approve before the full study.",
  "thesis/research": "Finished research, written up as a thesis or paper.",
  project: "Something you built, such as a system or prototype, with its write-up.",
};

function sentenceFor(name: string): string | undefined {
  return TYPE_SENTENCES[typeKey(name)];
}

interface ManuscriptStepProps {
  recordTypes: RecordType[];
  typeId:      number | null;
  onTypeChange: (id: number) => void;
  upload:      ManuscriptUpload;
  onFile:      (file: File) => void;
  onRetry:     () => void;
  exactMatches?: ManuscriptMatch[];
  /** Said when Continue was pressed with no type chosen (IR-1088). */
  typeError?:  string;
  /** Said when Continue was pressed with no accepted manuscript. */
  fileError?:  string;
}

export function ManuscriptStep({ recordTypes, typeId, onTypeChange, upload, onFile, onRetry, exactMatches = [], typeError, fileError }: ManuscriptStepProps) {
  const [replacing, setReplacing] = useState(false);
  const uploading = upload.status === "uploading";

  // The dropzone (and its progress bar, which held focus) unmounts the moment
  // an upload finishes, which would drop a keyboard user to <body>. Catch focus
  // on the finished file's own action instead, one Tab from Continue.
  const replaceRef = useRef<HTMLButtonElement>(null);
  const wasUploading = useRef(false);
  useEffect(() => {
    const lostFocus = document.activeElement == null || document.activeElement === document.body;
    if (wasUploading.current && upload.status === "done" && lostFocus) replaceRef.current?.focus();
    wasUploading.current = upload.status === "uploading";
  }, [upload.status]);

  const dropzoneUpload: UploadState | null =
    upload.status === "uploading"
      ? { status: "uploading", fileName: upload.fileName, progress: upload.progress }
      : upload.status === "failed"
        ? { status: "failed", fileName: upload.fileName, error: upload.error, onRetry }
        : null;

  const accepted = acceptedManuscript(upload);
  const showZone = upload.status !== "done" || replacing;

  return (
    <div className="flex flex-col gap-section-lg">
      <fieldset
        role="radiogroup"
        aria-invalid={typeError ? true : undefined}
        aria-describedby={typeError ? "publish-type-error" : undefined}
      >
        <legend className="text-heading font-semibold text-stone-900">What are you publishing?</legend>
        <div className="mt-3 grid gap-3 sm:grid-cols-3">
          {recordTypes.map((type) => {
            const checked = type.id === typeId;
            const sentence = sentenceFor(type.name);
            return (
              <label
                key={type.id}
                className={cn(
                  "flex cursor-pointer items-start gap-3 rounded-xl border p-card-compact transition-colors duration-150 motion-reduce:transition-none",
                  "has-[:focus-visible]:ring-2 has-[:focus-visible]:ring-brand has-[:focus-visible]:ring-offset-2",
                  checked ? SELECTED : "border-stone-200 bg-white hover:border-stone-400",
                  uploading && "cursor-not-allowed opacity-60",
                )}
              >
                <input
                  type="radio"
                  name="publish-record-type"
                  value={type.id}
                  checked={checked}
                  disabled={uploading}
                  onChange={() => onTypeChange(type.id)}
                  aria-describedby={sentence ? `publish-type-${type.id}-note` : undefined}
                  className="mt-1 h-4 w-4 shrink-0 accent-brand focus:outline-none"
                />
                <span>
                  <span className="block text-body font-semibold text-stone-900">{type.name}</span>
                  {sentence && (
                    <span id={`publish-type-${type.id}-note`} className="mt-0.5 block text-small text-stone-600">
                      {sentence}
                    </span>
                  )}
                </span>
              </label>
            );
          })}
        </div>
        {typeError && (
          <div role="alert" className="mt-2">
            <FieldError id="publish-type-error">{typeError}</FieldError>
          </div>
        )}
      </fieldset>

      <section aria-labelledby="publish-manuscript-heading">
        {exactMatches.length > 0 && (
          <div role="alert" className="rounded-lg border border-stone-300 bg-surface p-4">
            <p className="font-semibold">This manuscript is already attached to a record you can read.</p>
            <ul className="mt-2 space-y-2">
              {exactMatches.map((match) => <li key={match.id}>
                <Link to={match.action === "resume_draft" ? `/?publish=${match.id}` : match.url} className={cn("underline", FOCUS_RING)}>
                  {match.action === "resume_draft" ? "Resume draft" : "Open record"}: {match.title}
                </Link>
              </li>)}
            </ul>
          </div>
        )}
        <h3 id="publish-manuscript-heading" className="text-heading font-semibold text-stone-900">
          Manuscript file
        </h3>
        <p className="mt-1 text-small text-stone-600">
          The full paper as a PDF. Nothing else is needed now: if a reviewer needs another document, they'll ask.
        </p>

        {/* The dropzone announces the start; it is gone by the end, so the
            finish is announced here. Empty for a resumed draft, which has
            nothing new to say. */}
        <span role="status" className="sr-only">
          {upload.status === "done" && upload.fileName
            ? `${upload.fileName} uploaded`
            : upload.status === "failed" && accepted
              ? `${accepted.fileName ?? "Your manuscript"} is still attached`
              : ""}
        </span>

        {accepted && (
          <div className="mt-3 flex flex-wrap items-center gap-3 rounded-xl border border-stone-200 bg-white px-4 py-3">
            <i className="fas fa-file-pdf text-xl text-stone-600" aria-hidden />
            <p className="min-w-0 flex-1 text-body text-stone-800">
              <i className="fas fa-circle-check mr-1.5 text-stone-900" aria-hidden />
              <span className="font-medium break-all">{accepted.fileName ?? "Your manuscript"}</span>{" "}
              {upload.status === "failed"
                ? "is still attached"
                : accepted.fileName
                  ? "uploaded"
                  : "was uploaded earlier"}
              {accepted.size != null && <span className="text-stone-600"> · {formatBytes(accepted.size)}</span>}
            </p>
            {upload.status === "done" && !replacing && (
              <Button ref={replaceRef} type="button" variant="outline" size="sm" onClick={() => setReplacing(true)}>
                Replace file
              </Button>
            )}
          </div>
        )}

        {showZone && (
          <div className="mt-3">
            <UploadDropzone
              label="Upload manuscript"
              accept=".pdf"
              validate
              maxBytes={MANUSCRIPT_MAX_BYTES}
              disabled={typeId == null}
              hint={typeId == null ? "Choose what you're publishing first. PDF, up to 50 MB." : undefined}
              upload={dropzoneUpload}
              onFiles={([file]) => {
                setReplacing(false);
                onFile(file);
              }}
            />
          </div>
        )}

        {fileError && (
          <div role="alert" className="mt-2">
            <FieldError id="publish-file-error">{fileError}</FieldError>
          </div>
        )}
      </section>
    </div>
  );
}
