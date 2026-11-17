/**
 * The review page's Documents tab (IR-1203), for authors and reviewers. It
 * replaces the "All documents" drawer (IR-879), which held the Files section
 * (IR-411) as it was.
 *
 * Everything filed with the record, one compact `DocumentRow` each: the
 * manuscript, each document slot with its versions, what reviewers have asked
 * for, and any supplementary attachment.
 *
 * - **One upload path.** Every upload goes through `UploadDropzone`. A request
 *   for a slot is answered by uploading into that slot (IR-346), so a
 *   requested slot takes an upload even while the record is in review. An
 *   "Other" item has no slot, so it gets an upload of its own.
 * - **One vocabulary.** Each requested document reads Requested → Uploaded ·
 *   awaiting review → Accepted, or Replacement needed with the reviewer's
 *   reason (`document-requests/itemStatus`).
 *
 * The page decides who is looking: `owner`, `editable` (the `edit_details`
 * capability, so a draft or a record awaiting revision), `reviewing`, and
 * `attach` (the `attach_file` capability: an office filing a supplementary
 * file of its own, decided 2026-10-06). Remove follows each file's
 * server-computed `can_remove` (IR-476). This component decides nothing by
 * role. The server re-checks every upload and removal.
 */
import { useCallback, useEffect, useState } from "react";

import { documentsApi } from "@/api/documents";
import { recordsApi } from "@/api/records";
import { ConfirmDialog } from "@/components/shared/ConfirmDialog";
import { UploadDropzone, type UploadState } from "@/components/shared/UploadDropzone";
import { Skeleton } from "@/components/ui/Skeleton";
import { FOCUS_RING } from "@/components/ui/interaction";
import { PILL_SECONDARY } from "@/components/ui/pillStyles";
import { cn, downloadBlob, formatDate } from "@/lib/utils";
import type { RecordFile, RecordUpload, SlotWithUploads } from "@/types/documents";
import type { DocumentRequest, DocumentRequestItem, RecordDetail } from "@/types/records";

import { errorDetail, fieldError } from "@/lib/errorDetail";
import { ItemStatusChip, itemStatus } from "@/features/document-requests/itemStatus";
import { ReviewerDocumentRequests } from "@/features/document-requests/ReviewerDocumentRequests";

import { DocumentRow } from "./DocumentRow";
import { SectionHeading } from "./headings";

const PDF_LIMIT = 50 * 1024 * 1024;

interface DocumentsTabProps {
  record:    Pick<
    RecordDetail,
    "id" | "abstract_file" | "can_request_document" | "current_holders" | "manuscript_unsubmitted" | "versions"
  >;
  /** The viewer owns the record: they upload what is asked for. */
  owner:     boolean;
  /** The owner may add or replace any document, not only a requested one. */
  editable:  boolean;
  /** The viewer takes part in the review: they ask for and decide documents. */
  reviewing: boolean;
  /**
   * The viewer may attach a supplementary file of any type. Removing one is
   * per file, by the server's `can_remove` (IR-476): only the office that
   * filed it, while it takes part.
   */
  attach:    boolean;
  /**
   * The owner may upload a revised manuscript for the next version (the
   * `replace_manuscript` capability, IR-273).
   */
  replaceManuscript?: boolean;
  /** Told after anything changes, so the page can re-read what derives from it. */
  onChanged?: () => void;
}

/** A requested item, with who asked and whether that request is still open. */
interface Asked {
  item:  DocumentRequestItem;
  asker: string;
  open:  boolean;
}

/** Waiting on the owner: nothing uploaded yet, or the last upload refused. */
const needsUpload = (asked: Asked) => {
  const status = itemStatus(asked.item);
  return asked.open && (status === "requested" || status === "replacement_needed");
};

/**
 * What has been asked for, newest last, with an open request winning over a
 * closed one for the same slot. Withdrawn requests ask for nothing (IR-263).
 */
function askedFor(requests: DocumentRequest[]): { bySlot: Map<number, Asked>; other: Asked[] } {
  const bySlot = new Map<number, Asked>();
  const other: Asked[] = [];
  const live = requests
    .filter((r) => r.state !== "withdrawn")
    .sort((a, b) => Number(a.state === "open") - Number(b.state === "open"));
  for (const r of live) {
    for (const item of r.items) {
      const asked = { item, asker: r.label, open: r.state === "open" };
      if (item.slot == null) other.push(asked);
      else bySlot.set(item.slot, asked);
    }
  }
  return { bySlot, other };
}

async function saveBlob(fetch: () => Promise<{ data: unknown }>, filename: string) {
  const { data } = await fetch();
  downloadBlob(data as Blob, filename);
}

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

export function DocumentsTab({
  record,
  owner,
  editable,
  reviewing,
  attach,
  replaceManuscript = false,
  onChanged,
}: DocumentsTabProps) {
  const [slots, setSlots] = useState<SlotWithUploads[] | null>(null);
  const [files, setFiles] = useState<RecordFile[]>([]);
  const [requests, setRequests] = useState<DocumentRequest[]>([]);
  const [failed, setFailed] = useState(false);
  const [uploads, setUploads] = useState<Record<string, UploadState | undefined>>({});
  const [notice, setNotice] = useState<string | null>(null);
  // Every removal asks first (IR-872): a removed file is gone from storage.
  const [removing, setRemoving] = useState<{ name: string; run: () => Promise<void> } | null>(null);
  const [removeBusy, setRemoveBusy] = useState(false);
  const [removeError, setRemoveError] = useState<string | null>(null);
  const askToRemove = (name: string, run: () => Promise<void>) => {
    setRemoveError(null);
    setRemoving({ name, run });
  };
  const confirmRemove = async () => {
    if (!removing) return;
    setRemoveBusy(true);
    try {
      await removing.run();
      setRemoving(null);
    } catch (err) {
      setRemoveError(errorDetail(err, `Could not remove ${removing.name}. Please try again.`));
    } finally {
      setRemoveBusy(false);
    }
  };

  const load = useCallback(async () => {
    try {
      const [slotsRes, filesRes] = await Promise.all([
        documentsApi.slotsForRecord(record.id),
        documentsApi.files(record.id),
      ]);
      setSlots(slotsRes.data);
      const list = filesRes.data as RecordFile[] | { results?: RecordFile[] };
      setFiles(Array.isArray(list) ? list : list.results ?? []);
      setFailed(false);
    } catch {
      setFailed(true);
    }
    // Only participants may read requests (IR-349); for anyone else this
    // refuses, and there is simply nothing asked for to show.
    if (owner || reviewing) {
      try {
        const { data } = await recordsApi.documentRequests(record.id);
        setRequests(data);
      } catch {
        setRequests([]);
      }
    }
  }, [record.id, owner, reviewing]);

  useEffect(() => {
    void load();
  }, [load]);

  const changed = async () => {
    await load();
    onChanged?.();
  };

  /** Upload one file under `key`, keeping the dropzone's progress and retry. */
  const send = async (key: string, file: File, post: (onProgress: (p: number) => void) => Promise<unknown>) => {
    setUploads((u) => ({ ...u, [key]: { status: "uploading", fileName: file.name, progress: 0 } }));
    try {
      await post((progress) =>
        setUploads((u) => {
          const current = u[key];
          return current?.status === "uploading" ? { ...u, [key]: { ...current, progress } } : u;
        }),
      );
      setUploads((u) => ({ ...u, [key]: undefined }));
      await changed();
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

  if (failed && slots == null) {
    return (
      <div role="alert" className="rounded-card border border-stone-300 bg-surface p-card text-small text-brand-dark">
        Could not load this record's files.{" "}
        <button type="button" onClick={() => void load()} className={cn("font-semibold underline", FOCUS_RING)}>
          Try again
        </button>
      </div>
    );
  }
  if (slots == null) return <Skeleton rows={6} label="Loading the files…" onRetry={() => void load()} />;

  const { bySlot, other } = askedFor(requests);
  const shownSlots = slots.filter((s) => editable || s.uploads.length > 0 || bySlot.has(s.id));
  const download = (fetch: () => Promise<{ data: unknown }>, filename: string) =>
    saveBlob(fetch, filename).catch(() => setNotice(`Could not download ${filename}. Please try again.`));
  const manuscript = record.versions?.[record.versions.length - 1] ?? null;
  /** A row's compact PDF upload, keeping its progress and retry under `key`. */
  const pdfUpload = (key: string, label: string, post: (file: File, onProgress: (p: number) => void) => Promise<unknown>) => (
    <UploadDropzone compact label={label} accept=".pdf" validate maxBytes={PDF_LIMIT} upload={uploads[key]}
      onFiles={([file]) => void send(key, file, (onProgress) => post(file, onProgress))} />
  );
  const downloadVersion = (name: string, u: RecordUpload) =>
    download(() => documentsApi.downloadUpload(u.id), `${name} v${u.version}.${extensionOf(u.file)}`);

  return (
    <div className="space-y-section">
      {reviewing && (
        <ReviewerDocumentRequests record={record} reviewing onChanged={() => void changed()} />
      )}

      <ul aria-label="Documents" className="divide-y divide-stone-200 rounded-card border border-stone-200 bg-white">
        <DocumentRow
          name="Manuscript"
          latest={record.abstract_file
            ? manuscript ? byline(manuscript.number, manuscript.created_by_name, manuscript.created_at) : "Uploaded"
            : null}
          note={record.manuscript_unsubmitted && (
            <span className="inline-flex items-center gap-1.5 font-semibold text-brand-dark">
              <i className="fas fa-file-pen text-2xs" aria-hidden />
              Revised, not yet submitted
            </span>
          )}
          actions={(record.abstract_file || replaceManuscript) && (
            <>
              {record.abstract_file && (
                <DownloadButton name="the manuscript"
                  onClick={() => download(() => recordsApi.manuscriptBlob(record.id), "manuscript.pdf")} />
              )}
              {/* A revision request is answered with a new version, which may
                  carry a revised manuscript (IR-273). Reviewers keep reading
                  the submitted one until the owner submits; the server allows
                  the replacement only to an owner, only while a revision is
                  asked for. */}
              {replaceManuscript && pdfUpload("manuscript", "Upload revised manuscript",
                (file, onProgress) => recordsApi.uploadManuscript(record.id, file, { onProgress }))}
            </>
          )}
        />
        {shownSlots.map((slot) => {
          const asked = bySlot.get(slot.id);
          const key = `slot:${slot.id}`;
          const canUpload = owner && (editable || (asked != null && needsUpload(asked)));
          // Newest first, as the server lists them.
          const [latest] = slot.uploads;
          return (
            <DocumentRow
              key={slot.id}
              name={slot.name}
              latest={latest ? byline(latest.version, latest.uploaded_by_name, latest.created_at) : null}
              status={asked && <ItemStatusChip item={asked.item} />}
              note={asked && <AskedNote asked={asked} />}
              actions={(latest || canUpload) && (
                <>
                  {latest && (
                    <DownloadButton name={`${slot.name} version ${latest.version}`} onClick={() => downloadVersion(slot.name, latest)} />
                  )}
                  {canUpload && pdfUpload(key, `Upload ${slot.name}`,
                    (file, onProgress) => documentsApi.upload(record.id, slot.id, file, { onProgress }))}
                </>
              )}
              versions={{
                count: slot.uploads.length,
                list: (
                  <Versions
                    name={slot.name}
                    uploads={slot.uploads}
                    removable={owner && editable}
                    onDownload={(u) => downloadVersion(slot.name, u)}
                    onRemove={(u) =>
                      askToRemove(`${slot.name} version ${u.version}`, async () => {
                        await documentsApi.deleteUpload(u.id);
                        await changed();
                      })
                    }
                  />
                ),
              }}
            />
          );
        })}
        {other.map((asked) => {
          const key = `item:${asked.item.id}`;
          return (
            <DocumentRow
              key={key}
              name={asked.item.label}
              // An Other item keeps no versions of its own: only whether it was answered.
              latest={itemStatus(asked.item) === "requested" ? null : "Uploaded"}
              status={<ItemStatusChip item={asked.item} />}
              note={<AskedNote asked={asked} />}
              actions={owner && needsUpload(asked) && pdfUpload(key, `Upload ${asked.item.label}`,
                (file, onProgress) => documentsApi.uploadForRequestItem(record.id, asked.item.id, file, { onProgress }))}
            />
          );
        })}
      </ul>
      {shownSlots.length === 0 && other.length === 0 && (
        <p className="text-small text-stone-600">
          No other documents yet. A document appears here once it is uploaded or a reviewer asks for it.
        </p>
      )}

      {(files.length > 0 || attach) && (
        <section className="space-y-3">
          <SectionHeading>Supplementary attachments</SectionHeading>
          {attach && (
            <UploadDropzone
              label="Attach a supplementary file"
              hint="Any file type. Filed by your office, alongside the author's documents."
              upload={uploads.attachment}
              onFiles={([file]) =>
                void send("attachment", file, (onProgress) =>
                  documentsApi.uploadRecordFile(record.id, file, { onProgress }),
                )
              }
            />
          )}
          {files.length > 0 && (
            <ul aria-label="Supplementary attachments" className="divide-y divide-stone-200 rounded-card border border-stone-200 bg-white">
              {files.map((f) => (
                <DocumentRow
                  key={f.id}
                  name={f.filename}
                  latest={[f.uploaded_by_name, formatDate(f.created_at)].filter(Boolean).join(" · ")}
                  actions={
                    <>
                      <DownloadButton name={f.filename} onClick={() => download(() => documentsApi.downloadFile(f.id), f.filename)} />
                      {f.can_remove && (
                        <RemoveButton
                          name={f.filename}
                          onClick={() =>
                            askToRemove(f.filename, async () => {
                              await documentsApi.deleteFile(f.id);
                              await changed();
                            })
                          }
                        />
                      )}
                    </>
                  }
                />
              ))}
            </ul>
          )}
        </section>
      )}

      <p role="status" className="text-small text-brand empty:hidden">
        {notice ?? ""}
      </p>

      <ConfirmDialog
        open={removing !== null}
        title={removing ? `Remove ${removing.name}?` : "Remove this file?"}
        message="The file is deleted from IRIS and can't be restored. To correct a document, you can upload a new version instead."
        confirmLabel="Remove"
        danger
        focusCancel
        confirming={removeBusy}
        error={removeError}
        onConfirm={() => void confirmRemove()}
        onCancel={() => setRemoving(null)}
      />
    </div>
  );
}

/**
 * The stored file's extension, lower-cased, so a version saves as what it is
 * ("png" for a scan, IR-1203). Slots took only PDFs until IR-1220, so a name
 * with none is a PDF.
 */
function extensionOf(path: string): string {
  const name = path.split("/").pop() ?? "";
  const dot = name.lastIndexOf(".");
  return dot > 0 && dot < name.length - 1 ? name.slice(dot + 1).toLowerCase() : "pdf";
}

/** A version in words, "v2 · Ana Cruz · Nov 3, 2026", leaving out a name the server did not give. */
function byline(version: number, by: string | null | undefined, at: string): string {
  return [`v${version}`, by, formatDate(at)].filter(Boolean).join(" · ");
}

/** Who asked for a document, and why its last upload was not accepted. */
function AskedNote({ asked }: { asked: Asked }) {
  return (
    <p>
      Requested by {asked.asker}.
      {itemStatus(asked.item) === "replacement_needed" && asked.item.rejection_reason && (
        <>
          {" "}
          {asked.asker} did not accept the last upload: “{asked.item.rejection_reason}”
        </>
      )}
    </p>
  );
}

function Versions({
  name,
  uploads,
  removable,
  onDownload,
  onRemove,
}: {
  /** The document's name, so each version's controls are named apart. */
  name: string;
  uploads: RecordUpload[];
  removable: boolean;
  onDownload: (upload: RecordUpload) => void;
  onRemove: (upload: RecordUpload) => void;
}) {
  if (uploads.length === 0) return null;
  return (
    <ul aria-label={`Versions of ${name}`} className="divide-y divide-stone-100">
      {uploads.map((u) => (
        <li key={u.id} className="flex flex-wrap items-center justify-between gap-2 py-2 first:pt-0 last:pb-0">
          <span className="text-small text-stone-700">
            <span className="font-semibold text-stone-900">Version {u.version}</span>
            {" · "}
            {[u.uploaded_by_name, formatDate(u.created_at)].filter(Boolean).join(" · ")}
          </span>
          <span className="flex items-center gap-2">
            <DownloadButton name={`${name} version ${u.version}`} onClick={() => onDownload(u)} />
            {removable && !u.delete_refused && (
              <RemoveButton name={`${name} version ${u.version}`} onClick={() => onRemove(u)} />
            )}
            {removable && u.delete_refused && (
              // The server's own reason (ADR-058 §2, IR-872): part of the review, so kept.
              <span className="inline-flex items-center gap-1 text-small text-stone-600">
                <i className="fas fa-lock text-2xs" aria-hidden />
                Kept
                <span className="sr-only">: {u.delete_refused}</span>
              </span>
            )}
          </span>
        </li>
      ))}
    </ul>
  );
}

function DownloadButton({ name, onClick }: { name: string; onClick: () => void }) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-label={`Download ${name}`}
      className={cn(PILL_SECONDARY, FOCUS_RING, "reading-split:min-h-9 px-3")}
    >
      <i className="fas fa-download text-2xs" aria-hidden />
      Download
    </button>
  );
}

function RemoveButton({ name, onClick }: { name: string; onClick: () => void }) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-label={`Remove ${name}`}
      className={cn(PILL_SECONDARY, FOCUS_RING, "reading-split:min-h-9 px-3")}
    >
      <i className="fas fa-trash-can text-2xs" aria-hidden />
      Remove
    </button>
  );
}
