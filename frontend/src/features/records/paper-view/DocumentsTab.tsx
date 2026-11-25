/**
 * The review page's Documents tab (IR-1203), for authors and reviewers. It
 * replaces the "All documents" drawer (IR-879), which held the Files section
 * (IR-411) as it was.
 *
 * Everything filed with the record, one compact `DocumentRow` each: the
 * manuscript, each document slot with its versions, what reviewers have asked
 * for, and any supplementary attachment. Each of RDCO's requirements, and
 * the manuscript, carries its Required/Optional label and its Template, read
 * from Guidelines' list (IR-973, ADR-063 decision 6).
 *
 * - **One upload path.** Every upload goes through `UploadDropzone`. A request
 *   for a slot is answered by uploading into that slot (IR-346), so a
 *   requested slot takes an upload even while the record is in review. An
 *   "Other" item has no slot, so it gets an upload of its own.
 * - **One vocabulary.** Each requested document reads Requested → Uploaded ·
 *   awaiting review → Accepted, or Replacement needed with the reviewer's
 *   reason (`document-requests/itemStatus`).
 *
 * - **One place to answer a request** (IR-1318, IR-1322). The owner uploads
 *   what reviewers ask for here, not on the Overview. While anything is asked
 *   for, every slot takes an upload, and each upload stays the owner's alone,
 *   marked *Added, not sent yet* with a trash can, until they submit
 *   (ADR-022 Amendment 8). The top of the tab (`SubmitChangesBar`) names who
 *   asked and what is not sent yet: *Submit new version* while a revision is
 *   open, *Submit added documents* otherwise, grey until there is something.
 *
 * The page decides who is looking: `owner`, `editable` (the `edit_details`
 * capability, so a draft or a record awaiting revision), `reviewing`, and
 * `attach` (the `attach_file` capability: an office filing a supplementary
 * file of its own, decided 2026-10-06). Remove follows each file's
 * server-computed `can_remove` (IR-476). This component decides nothing by
 * role. The server re-checks every upload and removal.
 */
import { useCallback, useEffect, useState, type ReactNode } from "react";

import { documentsApi } from "@/api/documents";
import { recordsApi } from "@/api/records";
import { ConfirmDialog } from "@/components/shared/ConfirmDialog";
import { UploadDropzone } from "@/components/shared/UploadDropzone";
import { Skeleton } from "@/components/ui/Skeleton";
import { COLOUR_TRANSITION, FOCUS_RING } from "@/components/ui/interaction";
import { Tooltip } from "@/components/ui/Tooltip";
import { useLiveRefresh } from "@/hooks/useLiveRefresh";
import { SMALL_ACTION_PILL, SMALL_ACTION_TARGET } from "@/components/ui/pillStyles";
import { cn, downloadBlob, formatDate, joinLabels } from "@/lib/utils";
import type { RecordFile, RecordUpload, SlotWithUploads } from "@/types/documents";
import type { DocumentRequest, DocumentRequestItem, RecordDetail } from "@/types/records";

import { errorDetail } from "@/lib/errorDetail";
import { ItemStatusChip, itemStatus } from "@/features/document-requests/itemStatus";
import { ReviewerDocumentRequests } from "@/features/document-requests/ReviewerDocumentRequests";
import {
  GuideUnavailable, ManuscriptTemplate, RequirementTemplate, useRequirementGuide,
} from "@/features/guidelines/requirementGuide";

import { CONTROL_SIZE } from "./controls";
import { DocumentRow, byline } from "./DocumentRow";
import { useReviewPane } from "./reviewPane";
import { extensionOf, opensInReader, readerFormat, slotUploadDocument, type ReaderDocument } from "./readerDocument";
import { SectionHeading } from "./headings";
import { useRowUploads } from "./rowUploads";
import { SubmitChangesBar, unsentChanges } from "./SubmitNewVersionBar";

/** What an office may attach (IR-1220, ADR-032 §10 as amended 2026-11-18). */
const SUPPLEMENTARY_TYPES = ".pdf,.docx,.png,.jpg,.jpeg";

interface DocumentsTabProps {
  record:    Pick<
    RecordDetail,
    "id" | "abstract_file" | "can_request_document" | "current_holders" | "manuscript_unsubmitted"
    | "record_type_name" | "versions"
  > & Partial<Pick<RecordDetail, "revision" | "pipeline_status">>;
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
  /**
   * Show a document in the reader instead of the manuscript (IR-1203), named
   * with the control that opened it, so focus can come back to it. Absent
   * where there is no reader; only PDFs offer it.
   */
  onOpen?: (document: ReaderDocument, opener: HTMLElement) => void;
  /**
   * Opens *Submit new version* (IR-1318), given only to an owner with the
   * `create_version` capability. With a revision open, the tab's top bar
   * offers it.
   */
  onSubmitNewVersion?: () => void;
}

/** The mark on a file no version carries yet (IR-1318). */
function NotYetSubmitted({ children }: { children: ReactNode }) {
  return (
    <span className="inline-flex items-center gap-1.5 font-semibold text-brand-dark">
      <i className="fas fa-file-pen text-2xs" aria-hidden />
      {children}
    </span>
  );
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
  // A draft asks nobody anything until its reviewer finishes (ADR-022 Amendment 9).
  const live = requests
    .filter((r) => r.state !== "withdrawn" && r.state !== "draft")
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

export function DocumentsTab({
  record,
  owner,
  editable,
  reviewing,
  attach,
  replaceManuscript = false,
  onChanged,
  onOpen,
  onSubmitNewVersion,
}: DocumentsTabProps) {
  const pane = useReviewPane();
  const guideRead = useRequirementGuide();
  const guide = guideRead.guide;
  const [slots, setSlots] = useState<SlotWithUploads[] | null>(null);
  const [files, setFiles] = useState<RecordFile[]>([]);
  const [requests, setRequests] = useState<DocumentRequest[]>([]);
  const [failed, setFailed] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const [sending, setSending] = useState(false);
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

  /** `quiet`: a live re-read (ADR-073, IR-1287), which keeps what is shown if it fails. */
  const load = useCallback(async (quiet = false) => {
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
      if (!quiet) setFailed(true);
    }
    // Only participants may read requests (IR-349); for anyone else this
    // refuses, and there is simply nothing asked for to show.
    if (owner || reviewing) {
      try {
        const { data } = await recordsApi.documentRequests(record.id);
        setRequests(data);
      } catch {
        if (!quiet) setRequests([]);
      }
    }
  }, [record.id, owner, reviewing]);

  useEffect(() => {
    void load();
  }, [load]);
  useLiveRefresh([`record:${record.id}`], () => { void load(true); });

  const changed = async () => {
    await load();
    onChanged?.();
  };

  const { uploads, send, pdfUpload } = useRowUploads(changed);

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
  // Upload only where it was asked for (IR-1325): every document while the
  // paper is a draft, otherwise just what a reviewer requested. A revision
  // asks for the manuscript, which its own row takes (`replaceManuscript`).
  const drafting = editable && record.pipeline_status === "draft";
  const shownSlots = slots.filter((s) => drafting || s.uploads.length > 0 || bySlot.has(s.id));
  // What the top of the tab says to the owner (IR-1318): a revision's bar,
  // else what reviewers still need uploaded.
  const revision = record.revision;
  const revisionOpen = (revision?.open.length ?? 0) > 0;
  const hint = owner && onSubmitNewVersion && revisionOpen ? revision?.new_version ?? null : null;
  // Who is asking, a party once whether it asked for a revision, documents or
  // both (ADR-022 Amendment 8, IR-1322).
  const documentAskers = requests.filter((r) => r.state === "open").map((r) => r.label);
  const askers = [...new Set([...(revision?.open ?? []).map((r) => r.label), ...documentAskers])];
  const heldNames = [...new Set(slots.filter((s) => s.uploads.some((u) => u.held)).map((s) => s.name))];
  const submitDocuments = async () => {
    setSending(true);
    setNotice(null);
    try {
      const { data } = await recordsApi.sendDocuments(record.id);
      setNotice(`${data.sent === 1 ? "1 document" : `${data.sent} documents`} sent to ${joinLabels(documentAskers)}.`);
      await changed();
    } catch (err) {
      setNotice(errorDetail(err, "Could not send your documents. Nothing was sent. Please try again."));
    } finally {
      setSending(false);
    }
  };
  const download = (fetch: () => Promise<{ data: unknown }>, filename: string) =>
    saveBlob(fetch, filename).catch(() => setNotice(`Could not download ${filename}. Please try again.`));
  const manuscript = record.versions?.[record.versions.length - 1] ?? null;
  const downloadVersion = (name: string, u: RecordUpload) =>
    download(() => documentsApi.downloadUpload(u.id), `${name} v${u.version}.${extensionOf(u.file)}`);
  /** Shows `document` in the reader, making room for it when the pane covers the paper. */
  const open = (document: ReaderDocument, opener: HTMLElement) => {
    onOpen?.(document, opener);
    pane?.showReader();
  };
  /**
   * Opening a slot version, when there is a reader and the version is a PDF:
   * its title in the versions list opens it (IR-1325), with no Open button.
   * A slot's upload is a PDF, served as one, so only a PDF version opens
   * (images are attachments only). `newest`: the version a reviewer may open
   * a thread on from the reader (IR-1204).
   */
  const openVersion = (name: string, u: RecordUpload, newest: boolean) =>
    onOpen && readerFormat(u.file) === "pdf"
      ? (opener: HTMLElement) => open(slotUploadDocument(name, u, extensionOf(u.file), newest), opener)
      : null;

  return (
    <div className="space-y-section">
      {owner && hint && onSubmitNewVersion ? (
        <SubmitChangesBar mode="version" askers={askers} hint={hint} changes={unsentChanges(hint)} onSubmit={onSubmitNewVersion} />
      ) : owner && !revisionOpen && (documentAskers.length > 0 || heldNames.length > 0) && (
        <SubmitChangesBar
          mode="documents"
          askers={documentAskers.length > 0 ? [...new Set(documentAskers)] : ["your reviewers"]}
          changes={heldNames}
          sending={sending}
          onSubmit={() => void submitDocuments()}
        />
      )}
      {reviewing && (
        <ReviewerDocumentRequests record={record} reviewing onChanged={() => void changed()} />
      )}

      <GuideUnavailable read={guideRead} />
      <ul aria-label="Documents" className="divide-y divide-stone-200 rounded-card border border-stone-200 bg-white">
        <DocumentRow
          name="Manuscript"
          required={guide ? true : undefined}
          template={<ManuscriptTemplate recordType={guide?.recordType({ name: record.record_type_name }) ?? null} />}
          latest={record.abstract_file
            ? manuscript ? byline(manuscript.number, manuscript.created_by_name, manuscript.created_at) : "Uploaded"
            : null}
          note={record.manuscript_unsubmitted && <NotYetSubmitted>Revised, not yet submitted</NotYetSubmitted>}
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
          const canUpload = owner && (drafting || (asked != null && needsUpload(asked)));
          // Newest first, as the server lists them.
          const [latest] = slot.uploads;
          const requirement = guide?.requirement(slot.id) ?? null;
          return (
            <DocumentRow
              key={slot.id}
              name={slot.name}
              required={requirement?.is_required}
              template={<RequirementTemplate requirement={requirement} />}
              latest={latest ? byline(latest.version, latest.uploaded_by_name, latest.created_at) : null}
              status={asked && <ItemStatusChip item={asked.item} />}
              // Who asked, and whether the newest file is still the owner's
              // alone: added, not sent yet (ADR-022 Amendment 8, IR-1322).
              note={(asked || latest?.held) && (
                <>
                  {asked && <AskedNote asked={asked} />}
                  {latest?.held && <NotYetSubmitted>Added, not sent yet</NotYetSubmitted>}
                </>
              )}
              // No Download here: each version, the newest too, is downloaded
              // from its own row in the versions list (IR-1330).
              actions={((owner && latest?.held) || canUpload) && (
                <>
                  {owner && latest?.held && (
                    <RemoveButton name={`${slot.name} version ${latest.version}`} onClick={() =>
                      askToRemove(`${slot.name} version ${latest.version}`, async () => {
                        await documentsApi.deleteUpload(latest.id);
                        await changed();
                      })} />
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
                    removable={(u) => owner && (editable || u.held === true)}
                    openable={(u) => openVersion(slot.name, u, u.id === latest?.id)}
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
          // Its file sits in a slot named for it, held like any other (IR-1322).
          const held = slots.some((s) => s.name === asked.item.label && s.uploads[0]?.held);
          return (
            <DocumentRow
              key={key}
              name={asked.item.label}
              // An Other item keeps no versions of its own: only whether it was answered.
              latest={itemStatus(asked.item) === "requested" ? null : "Uploaded"}
              status={<ItemStatusChip item={asked.item} />}
              note={<>
                <AskedNote asked={asked} />
                {held && <NotYetSubmitted>Added, not sent yet</NotYetSubmitted>}
              </>}
              actions={owner && needsUpload(asked) && !held && pdfUpload(key, `Upload ${asked.item.label}`,
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
              // The server checks the name and the first bytes too (IR-1220); this only spares a wasted upload.
              accept={SUPPLEMENTARY_TYPES}
              validate
              hint="PDF, Word (.docx), PNG or JPG. Filed by your office, alongside the author's documents."
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
                  // Its name opens it (IR-1325), as a version's title does.
                  onOpenName={onOpen && opensInReader(f.filename, "") ? (opener) => open({
                    kind: "file", id: f.id, label: f.filename, fileName: f.filename,
                  }, opener) : undefined}
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
  openable,
  onDownload,
  onRemove,
}: {
  /** The document's name, so each version's controls are named apart. */
  name: string;
  uploads: RecordUpload[];
  /** Whether this viewer may remove a version: a draft's, or one still held (IR-1322). */
  removable: (upload: RecordUpload) => boolean;
  /** Opens a version in the reader (IR-1203), where it can be: its title is the control (IR-1325). */
  openable: (upload: RecordUpload) => ((opener: HTMLElement) => void) | null;
  onDownload: (upload: RecordUpload) => void;
  onRemove: (upload: RecordUpload) => void;
}) {
  if (uploads.length === 0) return null;
  return (
    <ul aria-label={`Versions of ${name}`} className="divide-y divide-stone-100">
      {uploads.map((u) => {
        const opens = openable(u);
        return (
        <li key={u.id} className="flex flex-wrap items-center justify-between gap-2 py-2 first:pt-0 last:pb-0">
          <span className="text-small text-stone-700">
            {opens ? (
              <button
                type="button"
                onClick={(e) => opens(e.currentTarget)}
                aria-label={`Open ${name} version ${u.version}`}
                className={cn(CONTROL_SIZE, "rounded-control font-semibold text-brand underline-offset-2 hover:underline", FOCUS_RING)}
              >
                Version {u.version}
              </button>
            ) : (
              <span className="font-semibold text-stone-900">Version {u.version}</span>
            )}
            {" · "}
            {[u.uploaded_by_name, formatDate(u.created_at)].filter(Boolean).join(" · ")}
          </span>
          <span className="flex items-center gap-2">
            <DownloadButton name={`${name} version ${u.version}`} onClick={() => onDownload(u)} />
            {removable(u) && !u.delete_refused && (
              <RemoveButton name={`${name} version ${u.version}`} onClick={() => onRemove(u)} />
            )}
            {removable(u) && u.delete_refused && (
              // The server's own reason (ADR-058 §2, IR-872): part of the review, so kept.
              <span className="inline-flex items-center gap-1 text-small text-stone-600">
                <i className="fas fa-lock text-2xs" aria-hidden />
                Kept
                <span className="sr-only">: {u.delete_refused}</span>
              </span>
            )}
          </span>
        </li>
        );
      })}
    </ul>
  );
}

/**
 * One action on a row's document: an icon and a verb, named for the document
 * it acts on ("Download Consent Paper version 2"), drawn as a small pill in a
 * full-size target (IR-1325). Hands back the button pressed, so a caller can
 * return focus to it.
 */
function RowAction({ icon, verb, name, onClick }: {
  icon: string;
  verb: string;
  name: string;
  onClick: (button: HTMLButtonElement) => void;
}) {
  return (
    <button
      type="button"
      onClick={(e) => onClick(e.currentTarget)}
      aria-label={`${verb} ${name}`}
      className={cn(SMALL_ACTION_TARGET, FOCUS_RING)}
    >
      <span className={SMALL_ACTION_PILL}>
        <i className={cn("fas text-2xs", icon)} aria-hidden />
        {verb}
      </span>
    </button>
  );
}

function DownloadButton({ name, onClick }: { name: string; onClick: () => void }) {
  return <RowAction icon="fa-download" verb="Download" name={name} onClick={onClick} />;
}

/**
 * Remove is a trash can alone (IR-1332), the one a draft has in My Library
 * (`DeleteRecord`): maroon, no fill or outline at rest, "Remove" as its
 * tooltip, and named for what it removes. Its target is the row actions' own,
 * 44px on touch and 36px beside a pointer, so the row does not grow.
 */
function RemoveButton({ name, onClick }: { name: string; onClick: () => void }) {
  return (
    <Tooltip label="Remove">
      <button
        type="button"
        onClick={onClick}
        aria-label={`Remove ${name}`}
        className={cn(
          "inline-flex min-h-11 min-w-11 reading-split:min-h-9 reading-split:min-w-9 items-center justify-center rounded-full",
          "text-brand hover:bg-stone-100 hover:text-brand-dark",
          COLOUR_TRANSITION,
          FOCUS_RING,
        )}
      >
        <i className="fas fa-trash-can" aria-hidden />
      </button>
    </Tooltip>
  );
}
