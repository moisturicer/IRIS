/**
 * Step 3 of the record creation/edit wizard.
 * Shows a manuscript control plus UploadSlots, one file per required slot.
 * Can be rendered without a recordId (AddRecord flow) -- in that case uploads
 * are queued locally and submitted after the record is created.
 *
 * TODO: persist staged files to sessionStorage so they survive accidental navigation.
 * TODO: show upload progress bar for large files.
 */
import { useEffect, useState } from "react";
import { recordsApi }      from "@/api/records";
import { documentsApi }    from "@/api/documents";
import { FileUploadZone }  from "@/components/shared/FileUploadZone";
import { Badge }           from "@/components/ui/Badge";
import { Spinner }         from "@/components/ui/Spinner";
import type { UploadSlot } from "@/types/documents";
import { FieldError }      from "./FieldError";

const MAX_PDF_BYTES = 50 * 1024 * 1024; // 50 MB — mirrors documents/views.py::MAX_PDF_SIZE_BYTES

/**
 * Reject before any request goes out — the server validates the same rules,
 * but IR-88's AC is explicit that this must happen "before upload starts".
 */
function validatePdf(file: File): string | null {
  if (!file.name.toLowerCase().endsWith(".pdf") || (file.type && file.type !== "application/pdf")) {
    return "Only PDF files are accepted.";
  }
  if (file.size > MAX_PDF_BYTES) {
    const mb = (file.size / (1024 * 1024)).toFixed(1);
    return `Your file is ${mb} MB. The limit is 50 MB.`;
  }
  return null;
}

interface UploadsStepProps {
  /** If provided, uploads go straight to the API for this record. */
  recordId?: number;
  /** Filter upload slots to only those configured for this record type. */
  recordTypeId?: number;
  /** Called whenever the local staged-file map changes (AddRecord flow). */
  onStagedChange?: (staged: Record<number, StagedFile>) => void;
  /** Called when a manuscript is staged (AddRecord flow, no recordId yet). */
  onManuscriptChange?: (file: File | null) => void;
  /**
   * Manuscript only, no per-type UploadSlot list. Used by the Submit
   * Disclosure wizard (ADR-018): only the manuscript is required at
   * submission — the real UploadSlot list is large (13 required items for
   * Thesis/Research) and unconditional, which works against NFR-U2 rather
   * than for it (IR-118). Everything else is attached later from the
   * record's own Documents page, once it's routed to the office that needs
   * it. EditRecordPage still wants the full list, so this defaults to false.
   */
  hideSlots?: boolean;
}

/**
 * A staged file's state. "Uploaded" is near-black and "Error" is maroon, the
 * brand's own colour, so the two that end a file's journey also carry a glyph
 * (IR-360). The word stays; the glyph is aria-hidden.
 */
function UploadState({ uploaded, error }: { uploaded?: boolean; error?: string }) {
  if (uploaded) {
    return (
      <Badge variant="success">
        <i className="fas fa-check mr-1" aria-hidden />Uploaded
      </Badge>
    );
  }
  if (error) {
    return (
      <Badge variant="danger">
        <i className="fas fa-circle-exclamation mr-1" aria-hidden />Error
      </Badge>
    );
  }
  return <Badge variant="neutral">Staged</Badge>;
}

export interface StagedFile {
  slotId:   number;
  file:     File;
  uploaded: boolean;
  error?:   string;
}

export function UploadsStep({ recordId, recordTypeId, onStagedChange, onManuscriptChange, hideSlots }: UploadsStepProps) {
  const [slots, setSlots]         = useState<UploadSlot[]>([]);
  const [loading, setLoading]     = useState(!hideSlots);
  const [staged, setStaged]       = useState<Record<number, StagedFile>>({});
  const [uploading, setUploading] = useState<Record<number, boolean>>({});

  const [manuscript, setManuscript]         = useState<{ file: File; error?: string; uploaded?: boolean } | null>(null);
  const [manuscriptBusy, setManuscriptBusy] = useState(false);

  useEffect(() => {
    if (hideSlots) return;
    setLoading(true);
    documentsApi
      .slots(recordTypeId)          // filter by record type when available
      .then(({ data }) => {
        // The global paginator wraps list responses in { results: [...] }.
        // Handle both the paginated envelope and a raw array defensively.
        const list = Array.isArray(data)
          ? data
          : (data as unknown as { results: UploadSlot[] }).results ?? [];
        setSlots(list);
      })
      .finally(() => setLoading(false));
  }, [recordTypeId, hideSlots]);    // re-fetch when record type changes

  // Notify parent (AddRecordPage) whenever the staged map changes
  useEffect(() => {
    onStagedChange?.(staged);
  }, [staged, onStagedChange]);

  const stageManuscript = async (files: File[]) => {
    const file = files[0];
    if (!file) return;
    const error = validatePdf(file);
    if (error) {
      setManuscript({ file, error });
      return;
    }
    setManuscript({ file });
    if (recordId) {
      setManuscriptBusy(true);
      try {
        await recordsApi.uploadManuscript(recordId, file);
        setManuscript({ file, uploaded: true });
      } catch {
        setManuscript({ file, error: "Upload failed. Please try again." });
      } finally {
        setManuscriptBusy(false);
      }
    } else {
      onManuscriptChange?.(file);
    }
  };

  const removeManuscript = () => {
    setManuscript(null);
    onManuscriptChange?.(null);
  };

  const stageFile = (slotId: number, files: File[]) => {
    const file = files[0];
    if (!file) return;
    const error = validatePdf(file);
    if (error) {
      setStaged((prev) => ({ ...prev, [slotId]: { slotId, file, uploaded: false, error } }));
      return;
    }
    setStaged((prev) => ({ ...prev, [slotId]: { slotId, file, uploaded: false } }));
    if (recordId) uploadNow(slotId, file);
  };

  const uploadNow = async (slotId: number, file: File) => {
    if (!recordId) return;
    setUploading((prev) => ({ ...prev, [slotId]: true }));
    try {
      await documentsApi.upload(recordId, slotId, file);
      setStaged((prev) => ({
        ...prev,
        [slotId]: { ...prev[slotId], uploaded: true },
      }));
    } catch {
      setStaged((prev) => ({
        ...prev,
        [slotId]: { ...prev[slotId], error: "Upload failed." },
      }));
    } finally {
      setUploading((prev) => ({ ...prev, [slotId]: false }));
    }
  };

  const manuscriptCard = (
    <div className="border border-stone-200 rounded-xl overflow-hidden">
      <div className="flex items-center justify-between px-4 py-3 bg-stone-50 border-b border-stone-200">
        <div className="flex items-center gap-2">
          <span className="text-[13px] font-semibold text-stone-800">
            Full Research Manuscript / Final Paper
          </span>
          {/* A requirement, not a failure: soft maroon, so it does not wear
              the solid maroon an upload "Error" does (IR-360). */}
          <Badge variant="warning">Mandatory</Badge>
        </div>
        {manuscript && !manuscriptBusy && (
          <UploadState uploaded={manuscript.uploaded} error={manuscript.error} />
        )}
      </div>
      <div className="p-4">
        {manuscriptBusy ? (
          <div className="flex justify-center py-6"><Spinner /></div>
        ) : manuscript && !manuscript.error ? (
          <div className="flex items-center gap-3 px-3 py-2 bg-stone-50 rounded-lg border border-stone-200">
            <i className="fa fa-file-pdf text-stone-500" aria-hidden />
            <span className="text-[13px] text-stone-700 flex-1 truncate">{manuscript.file.name}</span>
            <button type="button" onClick={removeManuscript} className="text-stone-500 hover:text-brand text-[12px]" aria-label="Remove manuscript">
              <i className="fa fa-times" aria-hidden />
            </button>
          </div>
        ) : (
          <FileUploadZone onFiles={stageManuscript} accept=".pdf" hint="PDF only, up to 50 MB" />
        )}
        {manuscript?.error && <FieldError>{manuscript.error}</FieldError>}
      </div>
    </div>
  );

  if (loading) {
    return (
      <div className="flex justify-center py-10">
        <Spinner />
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-5">
      {!recordId && (
        <div className="px-4 py-3 bg-stone-50 border border-stone-200 rounded-xl text-[13px] text-stone-700">
          <i className="fa fa-info-circle mr-2" aria-hidden />
          {hideSlots
            ? "Your manuscript is uploaded once the record is saved."
            : "Files will be uploaded after the record is saved."}
        </div>
      )}

      {manuscriptCard}

      {hideSlots ? (
        <p className="text-[12px] text-stone-500 leading-relaxed">
          Other documents an office needs — an ethics clearance form, a similarity report — are
          requested once your disclosure is routed there, from this record's Documents page.
        </p>
      ) : slots.length === 0 ? (
        <p className="text-[13px] text-stone-500 text-center py-4">
          No additional documents are required for this type.
        </p>
      ) : (
        slots.map((slot) => {
          const file = staged[slot.id];
          const isUp = uploading[slot.id];

          return (
            <div key={slot.id} className="border border-stone-200 rounded-xl overflow-hidden">
              <div className="flex items-center justify-between px-4 py-3 bg-stone-50 border-b border-stone-200">
                <div className="flex items-center gap-2">
                  <span className="text-[13px] font-semibold text-stone-800">{slot.name}</span>
                  {/* Only mark what is genuinely required. Every slot used to
                      carry a badge, so an "Optional" one said nothing and a
                      "Required" one was false -- 37 of 41 slots claimed to be
                      required, nothing enforced it, and several (Patent Draft,
                      Patent Search Report) are outputs of KTTO's work that a
                      submitter cannot possibly attach. IR-118 dropped the claim;
                      this stops the UI making it. When an office states its real
                      list, set is_required and the badge returns by itself. */}
                  {slot.is_required && <Badge variant="warning">Required</Badge>}
                </div>
                {file && <UploadState uploaded={file.uploaded} error={file.error} />}
              </div>

              <div className="p-4">
                {isUp ? (
                  <div className="flex justify-center py-6">
                    <Spinner />
                  </div>
                ) : file && !file.error ? (
                  <div className="flex items-center gap-3 px-3 py-2 bg-stone-50 rounded-lg border border-stone-200">
                    <i className="fa fa-file text-stone-500" aria-hidden />
                    <span className="text-[13px] text-stone-700 flex-1 truncate">{file.file.name}</span>
                    <button
                      type="button"
                      onClick={() => setStaged((prev) => {
                        const next = { ...prev };
                        delete next[slot.id];
                        return next;
                      })}
                      aria-label={`Remove ${slot.name}`}
                      className="text-stone-500 hover:text-brand text-[12px]"
                    >
                      <i className="fa fa-times" aria-hidden />
                    </button>
                  </div>
                ) : (
                  <FileUploadZone
                    onFiles={(files) => stageFile(slot.id, files)}
                    accept=".pdf"
                    hint="PDF only, up to 50 MB"
                  />
                )}
                {file?.error && <FieldError>{file.error}</FieldError>}
              </div>
            </div>
          );
        })
      )}
    </div>
  );
}
