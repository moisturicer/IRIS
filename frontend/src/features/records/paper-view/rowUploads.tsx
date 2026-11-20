/**
 * The compact PDF upload a document row offers (IR-1203), and the progress and
 * Retry each row keeps under its own key, so two rows uploading at once never
 * share news. The Documents tab and Publish's Documents step (IR-973) both
 * upload through it.
 */
import { useState } from "react";

import { UploadDropzone, type UploadState } from "@/components/shared/UploadDropzone";
import { errorDetail, fieldError } from "@/lib/errorDetail";

const PDF_LIMIT = 50 * 1024 * 1024;

/**
 * Why the server refused an upload, or "Please try again." when it gave no
 * reason (a dropped connection, a 5xx). A document upload carries `detail`;
 * the manuscript goes up as a PATCH of the record, so DRF refuses it keyed by
 * field (`abstract_file`) with no `detail` (IR-1048). A fixed reason like
 * "unsupported active content" must show: retrying the same file can't help.
 */
function uploadRefusal(err: unknown): string {
  return errorDetail(err, "") || fieldError(err, "abstract_file", "file") || "Please try again.";
}

type Post = (onProgress: (progress: number) => void) => Promise<unknown>;

/** Every row's upload state, and `send`, which runs one upload and then `onDone`. */
export function useRowUploads(onDone: () => Promise<void>) {
  const [uploads, setUploads] = useState<Record<string, UploadState | undefined>>({});

  /** Upload one file under `key`, keeping the dropzone's progress and retry. */
  const send = async (key: string, file: File, post: Post) => {
    setUploads((u) => ({ ...u, [key]: { status: "uploading", fileName: file.name, progress: 0 } }));
    try {
      await post((progress) =>
        setUploads((u) => {
          const current = u[key];
          return current?.status === "uploading" ? { ...u, [key]: { ...current, progress } } : u;
        }),
      );
      setUploads((u) => ({ ...u, [key]: undefined }));
      await onDone();
    } catch (err) {
      setUploads((u) => ({
        ...u,
        [key]: {
          status: "failed",
          fileName: file.name,
          error: uploadRefusal(err),
          onRetry: () => void send(key, file, post),
        },
      }));
    }
  };

  /** A row's compact PDF upload, named `label`, keeping its progress and retry under `key`. */
  const pdfUpload = (key: string, label: string, post: (file: File, onProgress: (p: number) => void) => Promise<unknown>) => (
    <UploadDropzone compact label={label} accept=".pdf" validate maxBytes={PDF_LIMIT} upload={uploads[key]}
      onFiles={([file]) => void send(key, file, (onProgress) => post(file, onProgress))} />
  );

  return { uploads, send, pdfUpload };
}
