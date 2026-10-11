/**
 * Paper View's Files section (IR-411; spec §4.6, §4.10). It replaces the
 * Documents page.
 *
 * Everything filed with the record in one place: the manuscript, each
 * supporting document with its versions, what reviewers have asked for, and
 * any supplementary attachment.
 *
 * - **One upload path.** Every upload goes through `UploadDropzone`. A request
 *   for a slot is answered by uploading into that slot (IR-346), so a
 *   requested slot takes an upload even while the record is in review. An
 *   "Other" item has no slot, so it gets a dropzone of its own.
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
import { useCallback, useEffect, useId, useState, type ReactNode } from "react";
import { Link } from "react-router-dom";

import { documentsApi } from "@/api/documents";
import { recordsApi } from "@/api/records";
import { UploadDropzone, type UploadState } from "@/components/shared/UploadDropzone";
import { Skeleton } from "@/components/ui/Skeleton";
import { FOCUS_RING } from "@/components/ui/interaction";
import { PILL_SECONDARY } from "@/components/ui/pillStyles";
import { cn, downloadBlob, formatDate } from "@/lib/utils";
import type { RecordFile, RecordUpload, SlotWithUploads } from "@/types/documents";
import type { DocumentRequest, DocumentRequestItem, RecordDetail } from "@/types/records";

import { errorDetail } from "@/features/document-requests/errorDetail";
import { ItemStatusChip, itemStatus } from "@/features/document-requests/itemStatus";
import { ReviewerDocumentRequests } from "@/features/document-requests/ReviewerDocumentRequests";

import { SectionHeading } from "./headings";

const PDF_LIMIT = 50 * 1024 * 1024;

interface FilesSectionProps {
  record:    Pick<
    RecordDetail,
    "id" | "abstract_file" | "can_request_document" | "current_holders" | "manuscript_unsubmitted"
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

export function FilesSection({
  record,
  owner,
  editable,
  reviewing,
  attach,
  replaceManuscript = false,
  onChanged,
}: FilesSectionProps) {
  const [slots, setSlots] = useState<SlotWithUploads[] | null>(null);
  const [files, setFiles] = useState<RecordFile[]>([]);
  const [requests, setRequests] = useState<DocumentRequest[]>([]);
  const [failed, setFailed] = useState(false);
  const [uploads, setUploads] = useState<Record<string, UploadState | undefined>>({});
  const [notice, setNotice] = useState<string | null>(null);

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
          error: errorDetail(err, "Please try again."),
          onRetry: () => void send(key, file, post),
        },
      }));
    }
  };

  if (failed && slots == null) {
    return (
      <div role="alert" className="rounded-2xl border border-brand-200 bg-brand-50 p-card text-small text-brand-dark">
        Could not load this record's files.{" "}
        <button type="button" onClick={() => void load()} className={cn("font-semibold underline", FOCUS_RING)}>
          Try again
        </button>
      </div>
    );
  }
  if (slots == null) return <Skeleton rows={6} label="Loading the files…" />;

  const { bySlot, other } = askedFor(requests);
  const shownSlots = slots.filter((s) => editable || s.uploads.length > 0 || bySlot.has(s.id));
  const download = (fetch: () => Promise<{ data: unknown }>, filename: string) =>
    saveBlob(fetch, filename).catch(() => setNotice(`Could not download ${filename}. Please try again.`));

  return (
    <div className="space-y-section-lg">
      {reviewing && (
        <ReviewerDocumentRequests record={record} reviewing onChanged={() => void changed()} />
      )}

      <section>
        <SectionHeading>Manuscript</SectionHeading>
        {record.manuscript_unsubmitted && (
          <p className="mb-2 inline-flex items-center gap-2 rounded-full bg-brand-50 px-3 py-1 text-small font-semibold text-brand-dark">
            <i className="fas fa-file-pen text-2xs" aria-hidden />
            Revised, not yet submitted
          </p>
        )}
        {record.abstract_file ? (
          <div className="flex flex-wrap items-center justify-between gap-3">
            <p className="text-body text-stone-700">
              The manuscript is the paper itself.{" "}
              <Link
                to={`/records/${record.id}?section=paper`}
                className={cn("font-semibold text-brand hover:underline", FOCUS_RING)}
              >
                Read it in the Paper section
              </Link>
            </p>
            <DownloadButton
              name="the manuscript"
              onClick={() => download(() => recordsApi.manuscriptBlob(record.id), "manuscript.pdf")}
            />
          </div>
        ) : (
          <p className="text-body text-stone-600">No manuscript has been uploaded yet.</p>
        )}
        {/* A revision request is answered with a new version, which may carry
            a revised manuscript (IR-273). Reviewers keep reading the submitted
            one until the owner submits; the server allows the replacement
            only to an owner, only while a revision is asked for. */}
        {replaceManuscript && (
          <div className="mt-3">
            <UploadDropzone
              label="Upload revised manuscript"
              accept=".pdf"
              validate
              maxBytes={PDF_LIMIT}
              upload={uploads.manuscript}
              onFiles={([file]) =>
                void send("manuscript", file, (onProgress) =>
                  recordsApi.uploadManuscript(record.id, file, { onProgress }),
                )
              }
            />
          </div>
        )}
      </section>

      <section>
        <SectionHeading>Supporting documents</SectionHeading>
        {shownSlots.length === 0 ? (
          <p className="text-body text-stone-600">
            None yet. A document appears here once it is uploaded or a reviewer asks for it.
          </p>
        ) : (
          <div className="space-y-3">
            {shownSlots.map((slot) => {
              const asked = bySlot.get(slot.id);
              const key = `slot:${slot.id}`;
              const canUpload = owner && (editable || (asked != null && needsUpload(asked)));
              return (
                <DocumentCard key={slot.id} name={slot.name} asked={asked}>
                  {canUpload && (
                    <UploadDropzone
                      label={`Upload ${slot.name}`}
                      accept=".pdf"
                      validate
                      maxBytes={PDF_LIMIT}
                      upload={uploads[key]}
                      onFiles={([file]) =>
                        void send(key, file, (onProgress) =>
                          documentsApi.upload(record.id, slot.id, file, { onProgress }),
                        )
                      }
                    />
                  )}
                  <Versions
                    name={slot.name}
                    uploads={slot.uploads}
                    removable={owner && editable}
                    onDownload={(u) =>
                      download(() => documentsApi.downloadUpload(u.id), `${slot.name} v${u.version}.pdf`)
                    }
                    onRemove={async (u) => {
                      try {
                        await documentsApi.deleteUpload(u.id);
                        await changed();
                      } catch (err) {
                        setNotice(errorDetail(err, `Could not remove version ${u.version}. Please try again.`));
                      }
                    }}
                  />
                </DocumentCard>
              );
            })}
          </div>
        )}
      </section>

      {other.length > 0 && (
        <section>
          <SectionHeading>Other requested documents</SectionHeading>
          <div className="space-y-3">
            {other.map((asked) => {
              const key = `item:${asked.item.id}`;
              return (
                <DocumentCard key={asked.item.id} name={asked.item.label} asked={asked}>
                  {owner && needsUpload(asked) && (
                    <UploadDropzone
                      label={`Upload ${asked.item.label}`}
                      accept=".pdf"
                      validate
                      maxBytes={PDF_LIMIT}
                      upload={uploads[key]}
                      onFiles={([file]) =>
                        void send(key, file, (onProgress) =>
                          documentsApi.uploadForRequestItem(record.id, asked.item.id, file, { onProgress }),
                        )
                      }
                    />
                  )}
                </DocumentCard>
              );
            })}
          </div>
        </section>
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
            <ul className="divide-y divide-stone-200 rounded-2xl border border-stone-200 bg-white">
              {files.map((f) => (
                <li key={f.id} className="flex flex-wrap items-center justify-between gap-3 px-card-compact py-3">
                  <span className="min-w-0">
                    <span className="block truncate text-body font-medium text-stone-800">{f.filename}</span>
                    <span className="block text-small text-stone-600">
                      {[f.uploaded_by_name, formatDate(f.created_at)].filter(Boolean).join(" · ")}
                    </span>
                  </span>
                  <span className="flex items-center gap-2">
                    <DownloadButton name={f.filename} onClick={() => download(() => documentsApi.downloadFile(f.id), f.filename)} />
                    {f.can_remove && (
                      <RemoveButton
                        name={f.filename}
                        onClick={async () => {
                          try {
                            await documentsApi.deleteFile(f.id);
                            await changed();
                          } catch (err) {
                            setNotice(errorDetail(err, `Could not remove ${f.filename}. Please try again.`));
                          }
                        }}
                      />
                    )}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </section>
      )}

      <p role="status" className="text-small text-brand empty:hidden">
        {notice ?? ""}
      </p>
    </div>
  );
}

/** One document: its name, where any request for it stands, and what can be done. */
function DocumentCard({ name, asked, children }: { name: string; asked?: Asked; children: ReactNode }) {
  const headingId = useId();
  return (
    <section aria-labelledby={headingId} className="rounded-2xl border border-stone-200 bg-white p-card-compact sm:p-card space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h3 id={headingId} className="text-heading font-semibold text-stone-900">
          {name}
        </h3>
        {asked && <ItemStatusChip item={asked.item} />}
      </div>
      {asked && (
        <p className="text-small text-stone-600">
          Requested by {asked.asker}.
          {itemStatus(asked.item) === "replacement_needed" && asked.item.rejection_reason && (
            <>
              {" "}
              {asked.asker} did not accept the last upload: “{asked.item.rejection_reason}”
            </>
          )}
        </p>
      )}
      {children}
    </section>
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
            {removable && <RemoveButton name={`${name} version ${u.version}`} onClick={() => onRemove(u)} />}
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
      className={cn(PILL_SECONDARY, FOCUS_RING, "min-h-9 px-3")}
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
      className={cn(PILL_SECONDARY, FOCUS_RING, "min-h-9 px-3")}
    >
      <i className="fas fa-trash-can text-2xs" aria-hidden />
      Remove
    </button>
  );
}
