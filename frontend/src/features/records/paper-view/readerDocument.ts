import { documentsApi } from "@/api/documents";

/**
 * A supporting document that Review's reader shows instead of the manuscript
 * (IR-1203): a version of a document slot (`upload`) or a supplementary
 * attachment (`file`). Only PDFs open in the reader; Word and other files are
 * download-only. Highlights, Ask IRIS and review threads stay on the manuscript.
 */
export interface ReaderDocument {
  kind: "upload" | "file";
  id: number;
  /** How the reader names it, e.g. "Consent Paper · version 2". */
  label: string;
  /** The name a download of it is saved under. */
  fileName: string;
}

/**
 * A stored file's extension, lower-cased, so a document is opened and saved as
 * what it is. A name with no extension gives `fallback`: a slot's upload is a
 * PDF (slots took only PDFs until IR-1220), an attachment's may be anything.
 */
export function extensionOf(path: string, fallback = "pdf"): string {
  const name = path.split("/").pop() ?? "";
  const dot = name.lastIndexOf(".");
  return dot > 0 && dot < name.length - 1 ? name.slice(dot + 1).toLowerCase() : fallback;
}

/** Names one shown document, for the reader's own keys: "upload-12". */
export const readerDocumentKey = (document: Pick<ReaderDocument, "kind" | "id">) => `${document.kind}-${document.id}`;

/**
 * Each kind's routes: `view` hands the reader the bytes (`?inline=true`),
 * `download` saves a copy. Both are the documents app's, so every read goes
 * through its permission checks (IR-1200) and writes its audit event.
 */
export const DOCUMENT_ROUTES: Record<ReaderDocument["kind"], {
  view: (id: number, options?: { signal?: AbortSignal }) => Promise<{ data: Blob; headers?: Record<string, unknown> }>;
  download: (id: number) => Promise<{ data: Blob }>;
}> = {
  upload: { view: (id, options) => documentsApi.viewUpload(id, options), download: (id) => documentsApi.downloadUpload(id) },
  file: { view: (id, options) => documentsApi.viewFile(id, options), download: (id) => documentsApi.downloadFile(id) },
};

/** The reader opens PDFs; anything else is downloaded. */
export const opensInReader = (path: string, fallback?: string) => extensionOf(path, fallback) === "pdf";
