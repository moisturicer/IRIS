import { useId, useRef, useState, type DragEvent, type ReactNode } from "react";

import { documentsApi } from "@/api/documents";
import { recordsApi } from "@/api/records";
import { ConfirmDialog } from "@/components/shared/ConfirmDialog";
import { UploadDropzone, refuseFiles } from "@/components/shared/UploadDropzone";
import { Select } from "@/components/ui/Select";
import { COLOUR_TRANSITION, FOCUS_RING } from "@/components/ui/interaction";
import { PILL_PRIMARY, PILL_SECONDARY } from "@/components/ui/pillStyles";
import { ItemStatusChip, itemStatus } from "@/features/document-requests/itemStatus";
import { GuideUnavailable, RequirementTemplate, useRequirementGuide } from "@/features/guidelines/requirementGuide";
import type { Capability } from "@/features/records/capabilities";
import { errorDetail } from "@/lib/errorDetail";
import { cn, downloadBlob, joinLabels } from "@/lib/utils";
import type { DocumentRequest, RecordDetail } from "@/types/records";

import { WAITING_TARGET } from "../../waitingOnYou";
import { newVersionSummary } from "../NewVersionDialog";
import { useRowUploads } from "../rowUploads";

const ACCEPT = ".pdf";
const PDF_LIMIT = 50 * 1024 * 1024;

/** One file the owner can hand in. */
interface FileRow {
  key: string;
  label: string;
  /** Who asked, as the server words it; null for the manuscript, which answers every revision request. */
  asker: string | null;
  /** Still to be handed in: it takes a file. */
  open: boolean;
  note: ReactNode;
  chip: ReactNode;
  template: ReactNode;
  post: (file: File, onProgress: (p: number) => void) => Promise<unknown>;
  /** The file handed in, and what the owner may still do with it. */
  file: {
    download: () => Promise<{ data: Blob }>;
    /** Sends a corrected file, which its own control announces; null once it may no longer change. */
    replace: FileRow["post"] | null;
    /** Takes it back; null once it may no longer change. */
    remove: (() => Promise<unknown>) | null;
    /** What removing it does, said before it is done. */
    removing: string;
  } | null;
}

interface OwnerAnswerProps {
  record: RecordDetail;
  can: ReadonlySet<Capability>;
  /** The document requests shown: open, or fulfilled during this visit. */
  requests: DocumentRequest[];
  refreshFailed: string | null;
  /** Something was stored: read the requests and the record again. */
  onStored: () => Promise<void>;
  onSubmitNewVersion: () => void;
}

/**
 * The owner's half of the review's Overview: every file they have been asked
 * for, dropped here, and *Submit new version*. It holds no answers of its own:
 * a comment is answered in Review's Threads, which `OverviewComments` links to.
 *
 * A requested document goes to its reviewer as soon as it uploads. The revised
 * manuscript is stored, not sent: reviewers keep reading the submitted one
 * until the owner submits (IR-273). Each row says which. What is handed in can
 * be read, replaced and removed until whoever asked has decided it.
 *
 * A file dropped on a row goes there. One dropped on the field goes to the
 * only row left, or waits to be told which it is: a file name never decides,
 * since a wrong guess would send the wrong document to an office.
 */
export function OwnerAnswer({ record, can, requests, refreshFailed, onStored, onSubmitNewVersion }: OwnerAnswerProps) {
  const headingId = useId();
  const blockedId = useId();
  const guideRead = useRequirementGuide();
  const section = useRef<HTMLElement>(null);
  // Said here, not in the row: a row's own upload control goes once its file is in.
  const [said, setSaid] = useState("");
  const stored = async () => {
    const focused = section.current?.contains(document.activeElement) ?? false;
    await onStored();
    if (focused) requestAnimationFrame(() => { if (document.activeElement === document.body) section.current?.focus(); });
  };
  const { uploads, send, pdfUpload } = useRowUploads(stored);
  const telling = (post: FileRow["post"]): FileRow["post"] => async (file, onProgress) => {
    setSaid("");
    const result = await post(file, onProgress);
    setSaid(`${file.name} uploaded`);
    return result;
  };
  // Dropped on the field, and not yet told which file it is.
  const [waiting, setWaiting] = useState<{ key: number; file: File }[]>([]);
  const [refused, setRefused] = useState<string | null>(null);
  const [over, setOver] = useState<string | null>(null);
  const [removing, setRemoving] = useState<FileRow | null>(null);
  const [removeBusy, setRemoveBusy] = useState(false);
  const [problem, setProblem] = useState<string | null>(null);
  const download = async (row: FileRow) => {
    setProblem(null);
    try {
      if (row.file) downloadBlob((await row.file.download()).data, `${row.label}.pdf`);
    } catch {
      setProblem(`Could not download ${row.label}. Please try again.`);
    }
  };
  const remove = async () => {
    if (!removing?.file?.remove) return;
    setRemoveBusy(true);
    try {
      await removing.file.remove();
      setSaid(`${removing.label} removed`);
      setRemoving(null);
      setProblem(null);
      await stored();
    } catch (err) {
      setProblem(errorDetail(err, `Could not remove ${removing.label}. Please try again.`));
    } finally {
      setRemoveBusy(false);
    }
  };

  const revising = record.revision.open.length > 0;
  const hint = can.has("create_version") ? record.revision.new_version : null;
  const replace = revising && can.has("replace_manuscript");

  const rows: FileRow[] = [
    ...(replace ? [{
      key: "manuscript",
      label: "Revised manuscript",
      asker: null,
      open: !record.manuscript_unsubmitted,
      note: record.manuscript_unsubmitted ? "Ready, not yet submitted" : hint ? `Sent with v${hint.number}` : "Sent with your new version",
      chip: null,
      template: null,
      post: telling((file, onProgress) => recordsApi.uploadManuscript(record.id, file, { onProgress })),
      file: record.manuscript_unsubmitted ? {
        download: () => recordsApi.manuscriptBlob(record.id),
        replace: (file: File, onProgress: (p: number) => void) => recordsApi.uploadManuscript(record.id, file, { onProgress }),
        remove: can.has("discard_revised_manuscript") ? () => recordsApi.discardRevisedManuscript(record.id) : null,
        removing: "Your revised manuscript is deleted, and the paper goes back to the submitted one. No reviewer has seen it.",
      } : null,
    }] : []),
    ...requests.flatMap((request) => request.items.map((item) => {
      const status = itemStatus(item);
      const open = request.state === "open" && item.state === "missing";
      const upload = item.upload;
      return {
        key: `item:${item.id}`,
        label: item.label,
        asker: request.label,
        open,
        note: open && item.rejection_reason
          ? <span className="text-brand">{request.label} did not accept your last upload: “{item.rejection_reason}”</span>
          : open ? `For ${request.label}, sent as soon as it uploads` : `For ${request.label}`,
        chip: status === "requested" ? null : <ItemStatusChip item={item} />,
        template: <RequirementTemplate requirement={item.slot == null ? null : guideRead.guide?.requirement(item.slot) ?? null} />,
        post: telling((file, onProgress) => documentsApi.uploadForRequestItem(record.id, item.id, file, { onProgress })),
        file: upload == null ? null : {
          download: () => documentsApi.downloadUpload(upload),
          replace: item.can_replace
            ? (file: File, onProgress: (p: number) => void) => documentsApi.uploadForRequestItem(record.id, item.id, file, { onProgress, replaces: upload })
            : null,
          remove: item.can_replace ? () => recordsApi.removeDocumentRequestUpload(item.id, upload) : null,
          removing: `${request.label} has not decided on it yet. It is asked for again, and you can upload another file.`,
        },
      };
    })),
  ];
  const busy = (row: FileRow) => uploads[row.key]?.status === "uploading";
  const open = rows.filter((r) => r.open && !busy(r));
  // With one file left the field is that file's own control, so its row has none.
  const only = rows.filter((r) => r.open).length === 1 ? rows.find((r) => r.open)! : null;

  const sendTo = (row: FileRow, file: File) => void send(row.key, file, (onProgress) => row.post(file, onProgress));
  const take = (files: File[]) => {
    setRefused(null);
    if (only && files.length === 1) return sendTo(only, files[0]);
    setWaiting((was) => [...was, ...files.map((file, i) => ({ key: Date.now() + i, file }))]);
  };
  const dropOnRow = (row: FileRow, e: DragEvent) => {
    // The row's own Upload button is a drop target too, and has taken it.
    const taken = e.defaultPrevented;
    e.preventDefault();
    setOver(null);
    if (taken || !row.open || busy(row)) return;
    const files = Array.from(e.dataTransfer.files);
    const reason = files.length > 1
      ? `${row.label} takes one file. Drop the others on their own rows.`
      : refuseFiles(files, ACCEPT, PDF_LIMIT);
    setRefused(reason);
    if (!reason && files[0]) sendTo(row, files[0]);
  };

  const fulfilled = requests.filter((r) => r.state === "fulfilled");
  const documentAskers = [...new Set(requests.filter((r) => r.state === "open").map((r) => r.label))];
  const title = revising ? "Your new version" : rows.some((r) => r.open) ? "Your documents" : "Requested documents";

  if (rows.length === 0 && !hint) return null;
  return (
    <section
      ref={section}
      id={revising ? WAITING_TARGET.revision : WAITING_TARGET.document}
      tabIndex={-1}
      aria-labelledby={headingId}
      className={cn("scroll-mt-20 overflow-hidden rounded-card border border-stone-300 bg-surface", FOCUS_RING)}
    >
      <div className="px-5 py-5 overview-roomy:px-7">
        <h2 id={headingId} className="mb-3 font-display text-section font-semibold text-stone-900">{title}</h2>
        <span role="status" className="sr-only">{said}</span>
        {refreshFailed && <p role="alert" className="mb-3 text-small text-brand">{refreshFailed}</p>}
        <GuideUnavailable read={guideRead} what="The requested documents' Templates" />

        {rows.some((r) => r.open) && (
          <UploadDropzone
            label={only ? `Upload ${only.label}` : "Upload files"}
            accept={ACCEPT}
            validate
            multiple={!only}
            maxBytes={PDF_LIMIT}
            hint={only ? `${only.label}. PDF, up to 50 MB` : "PDF, up to 50 MB each. You say which file is which."}
            upload={only ? uploads[only.key] : null}
            onFiles={take}
          />
        )}
        {refused && <p role="alert" className="mt-2 text-small text-brand">{refused}</p>}

        {waiting.length > 0 && (
          <ul aria-label="Files to place" className="mt-3 divide-y divide-stone-200 rounded-card border border-stone-300 px-4">
            {waiting.map(({ key, file }) => {
              const drop = () => setWaiting((was) => was.filter((w) => w.key !== key));
              return (
                <li key={key} className="flex flex-wrap items-center gap-x-4 gap-y-2 py-3">
                  <span className="min-w-0 flex-1 basis-48 break-words text-body font-semibold text-stone-900">{file.name}</span>
                  {open.length > 0 ? (
                    <Select
                      label={`Which file is ${file.name}?`}
                      size="sm"
                      value=""
                      onChange={(e) => {
                        const row = open.find((r) => r.key === e.target.value);
                        if (!row) return;
                        drop();
                        sendTo(row, file);
                      }}
                    >
                      <option value="">Choose…</option>
                      {open.map((r) => <option key={r.key} value={r.key}>{r.asker ? `${r.label} (${r.asker})` : r.label}</option>)}
                    </Select>
                  ) : <p className="text-small text-stone-600">Every requested file is already in.</p>}
                  <button type="button" onClick={drop} aria-label={`Remove ${file.name}`}
                    className={cn("min-h-11 reading-split:min-h-9 rounded-control px-2 text-small font-semibold text-brand hover:underline", FOCUS_RING)}>
                    Remove
                  </button>
                </li>
              );
            })}
          </ul>
        )}

        {rows.length > 0 && (
          <ul
            id={revising && requests.length > 0 ? WAITING_TARGET.document : undefined}
            tabIndex={-1}
            aria-label="Requested files"
            className={cn("mt-4 divide-y divide-stone-200 rounded-control", FOCUS_RING)}
          >
            {rows.map((row) => (
              <li
                key={row.key}
                onDragOver={(e) => { e.preventDefault(); if (row.open && !busy(row)) setOver(row.key); }}
                onDragLeave={(e) => { if (!e.currentTarget.contains(e.relatedTarget as globalThis.Node | null)) setOver(null); }}
                onDrop={(e) => dropOnRow(row, e)}
                className={cn("flex flex-wrap items-center gap-x-4 gap-y-2 px-2 py-3", COLOUR_TRANSITION, over === row.key && "bg-brand/[0.07] ring-2 ring-brand rounded-control")}
              >
                <i className={cn("fas w-4 shrink-0 text-center", row.open ? "fa-file-lines text-stone-500" : "fa-check text-cleared")} aria-hidden />
                <div className="min-w-0 flex-1 basis-48">
                  <p className="break-words text-body font-semibold text-stone-900">{row.label}</p>
                  <p className="break-words text-small text-stone-600">{row.note}</p>
                  {row.template}
                </div>
                {row.chip}
                {row.open && row !== only && pdfUpload(row.key, `Upload ${row.key === "manuscript" ? "revised manuscript" : row.label}`, row.post)}
                {row.file && (
                  <div className="flex flex-wrap items-center gap-2">
                    <RowButton icon="fa-download" verb="Download" name={row.label} onClick={() => void download(row)} />
                    {row.file.replace && pdfUpload(row.key, `Replace ${row.label}`, row.file.replace, "Replace")}
                    {row.file.remove && !busy(row) && (
                      <RowButton icon="fa-trash-can" verb="Remove" name={row.label} onClick={() => { setProblem(null); setRemoving(row); }} />
                    )}
                  </div>
                )}
              </li>
            ))}
          </ul>
        )}
        {problem && !removing && <p role="alert" className="mt-2 text-small text-brand">{problem}</p>}
        {fulfilled.map((r) => (
          <p key={r.id} className="mt-2 text-small font-semibold text-stone-900">
            <i className="fas fa-circle-check mr-1.5 text-2xs text-cleared" aria-hidden />
            {r.state_label}. {r.label} has been told everything is uploaded.
          </p>
        ))}

      </div>

      {(hint || documentAskers.length > 0) && (
        <div className="flex flex-wrap items-center justify-between gap-x-6 gap-y-3 border-t border-stone-200 bg-stone-50 px-5 py-4 overview-roomy:px-7">
          <div className="min-w-0 flex-1 basis-64 space-y-1 text-small text-stone-700">
            {hint && <p>{newVersionSummary(hint)}</p>}
            {hint?.blocked && <p id={blockedId} className="text-brand">{hint.blocked}</p>}
            {documentAskers.length > 0 && (
              <p>{joinLabels(documentAskers)} {documentAskers.length === 1 ? "is" : "are"} told once everything they asked for is uploaded.</p>
            )}
          </div>
          {hint && (
            <button type="button" onClick={onSubmitNewVersion} aria-describedby={hint.blocked ? blockedId : undefined} className={cn(PILL_PRIMARY, FOCUS_RING)}>
              <i className="fas fa-paper-plane text-2xs" aria-hidden />
              Submit new version
            </button>
          )}
        </div>
      )}

      <ConfirmDialog
        open={removing !== null}
        title={`Remove ${removing?.label ?? "this file"}?`}
        message={removing?.file?.removing ?? ""}
        confirmLabel="Remove"
        danger
        focusCancel
        confirming={removeBusy}
        error={problem}
        onConfirm={() => void remove()}
        onCancel={() => { setRemoving(null); setProblem(null); }}
      />
    </section>
  );
}

/** One act on a handed-in file, named for the file it acts on. */
function RowButton({ icon, verb, name, onClick }: { icon: string; verb: string; name: string; onClick: () => void }) {
  return (
    <button type="button" onClick={onClick} aria-label={`${verb} ${name}`} className={cn(PILL_SECONDARY, "px-3 reading-split:min-h-9", FOCUS_RING)}>
      <i className={cn("fas text-2xs", icon)} aria-hidden />
      {verb}
    </button>
  );
}
