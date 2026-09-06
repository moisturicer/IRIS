import { useEffect, useRef, useState, useCallback } from "react";
import { Link, useParams } from "react-router-dom";
import { documentsApi } from "@/api/documents";
import { recordsApi }   from "@/api/records";
import { reviewsApi }   from "@/api/reviews";
import { PageHeader }   from "@/components/layout/PageHeader";
import { EmptyState }   from "@/components/shared/EmptyState";
import { FileUploadZone } from "@/components/shared/FileUploadZone";
import { Badge }        from "@/components/ui/Badge";
import { Spinner }      from "@/components/ui/Spinner";
import { useAuth }      from "@/hooks/useAuth";
import { useUIStore }   from "@/store/ui.store";
import { formatDate }   from "@/lib/utils";
import type { RecordUpload, UploadSlot, RecordFile } from "@/types/documents";
import type { RecordDetail } from "@/types/records";
import { Skeleton } from "@/components/ui/Skeleton";

// ---------------------------------------------------------------------------
// PDF viewer modal
// ---------------------------------------------------------------------------

interface PdfViewerProps {
  blobUrl:  string;
  filename: string;
  onClose:  () => void;
}

function PdfViewer({ blobUrl, filename, onClose }: PdfViewerProps) {
  return (
    <div
      className="fixed inset-0 z-50 flex flex-col bg-black/90"
      onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}
    >
      <div className="flex items-center justify-between px-4 py-3 bg-gray-900 text-white flex-shrink-0">
        <span className="text-[13px] font-medium truncate max-w-[80%]">{filename}</span>
        <div className="flex items-center gap-3 ml-4">
          <a
            href={blobUrl}
            download={filename}
            className="text-gray-300 hover:text-white text-[12px] flex items-center gap-1.5"
          >
            <i className="fas fa-download" aria-hidden /> Download
          </a>
          <button
            type="button"
            onClick={onClose}
            className="text-gray-300 hover:text-white text-[18px] leading-none"
            aria-label="Close viewer"
          >
            <i className="fas fa-times" aria-hidden />
          </button>
        </div>
      </div>
      <iframe
        src={blobUrl}
        className="flex-1 w-full border-0"
        title={filename}
      />
    </div>
  );
}

/** Statuses where the owner is still allowed to add / replace slot documents. */
const UPLOAD_ALLOWED_STATUSES = ["draft", "declined"];

interface SlotWithUploads extends UploadSlot {
  uploads: RecordUpload[];
}

// ---------------------------------------------------------------------------
// Auth-PIN modal
// ---------------------------------------------------------------------------

type PinStep = "idle" | "request" | "enter" | "verified";

interface AuthPinModalProps {
  recordId: number;
  userEmail: string;
  onClose:  () => void;
}

function AuthPinModal({ recordId, userEmail, onClose }: AuthPinModalProps) {
  const [step,       setStep]       = useState<PinStep>("request");
  const [pinInput,   setPinInput]   = useState("");
  const [busy,       setBusy]       = useState(false);
  const [errorMsg,   setErrorMsg]   = useState<string | null>(null);

  const handleSend = async () => {
    setBusy(true);
    setErrorMsg(null);
    try {
      await reviewsApi.generatePin(recordId);
      setStep("enter");
    } catch {
      setErrorMsg("Failed to send PIN. Please try again.");
    } finally {
      setBusy(false);
    }
  };

  const handleVerify = async () => {
    const cleaned = pinInput.trim().toUpperCase();
    if (!cleaned) { setErrorMsg("Please enter the PIN from your email."); return; }
    setBusy(true);
    setErrorMsg(null);
    try {
      await reviewsApi.verifyPin(recordId, cleaned);
      setStep("verified");
    } catch {
      setErrorMsg("Incorrect or already-used PIN. Check your email and try again.");
    } finally {
      setBusy(false);
    }
  };

  return (
    /* Backdrop */
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 px-4"
      onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}
    >
      <div className="bg-white rounded-2xl shadow-xl w-full max-w-sm p-6 space-y-4">
        {/* Header */}
        <div className="flex items-start justify-between">
          <div>
            <p className="text-[15px] font-bold text-gray-900">Document Access PIN</p>
            <p className="text-[12px] text-gray-500 mt-0.5">
              A one-time PIN will be emailed to you for verified access.
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="text-gray-500 hover:text-gray-600 text-[18px] leading-none ml-2 mt-0.5"
            aria-label="Close"
          >
            <i className="fas fa-times" aria-hidden />
          </button>
        </div>

        {/* Step: Request */}
        {step === "request" && (
          <div className="space-y-4">
            <div className="rounded-lg bg-gray-50 border border-gray-200 px-4 py-3 text-[13px] text-gray-700">
              A PIN will be sent to:
              <span className="font-semibold ml-1">{userEmail}</span>
            </div>
            {errorMsg && (
              <p className="text-[12px] text-red-500">{errorMsg}</p>
            )}
            <div className="flex gap-2 pt-1">
              <button
                type="button"
                onClick={onClose}
                className="flex-1 border border-gray-200 rounded-lg py-2 text-[13px] font-semibold text-gray-600 hover:bg-gray-50"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={handleSend}
                disabled={busy}
                className="flex-1 bg-[#6B0F12] text-white rounded-lg py-2 text-[13px] font-semibold hover:bg-[#7d1215] disabled:opacity-60 flex items-center justify-center gap-2"
              >
                {busy ? <><Spinner size="sm" /> Sending…</> : "Send PIN"}
              </button>
            </div>
          </div>
        )}

        {/* Step: Enter PIN */}
        {step === "enter" && (
          <div className="space-y-4">
            <div className="rounded-lg bg-green-50 border border-green-200 px-4 py-3 text-[13px] text-green-700">
              <i className="fas fa-check-circle mr-1.5" aria-hidden />
              PIN sent to <strong>{userEmail}</strong>. Check your inbox.
            </div>
            <div>
              <label className="block text-[12px] font-semibold text-gray-700 mb-1">
                Enter PIN
              </label>
              <input
                type="text"
                value={pinInput}
                onChange={(e) => setPinInput(e.target.value.toUpperCase())}
                onKeyDown={(e) => e.key === "Enter" && handleVerify()}
                placeholder="e.g. A3BX29"
                maxLength={10}
                autoFocus
                className="w-full border border-gray-200 rounded-lg px-3 py-2 text-[14px] font-mono tracking-widest text-center focus:outline-none focus:border-[#6B0F12]"
              />
            </div>
            {errorMsg && (
              <p className="text-[12px] text-red-500">{errorMsg}</p>
            )}
            <div className="flex gap-2">
              <button
                type="button"
                onClick={() => { setStep("request"); setPinInput(""); setErrorMsg(null); }}
                className="flex-1 border border-gray-200 rounded-lg py-2 text-[13px] font-semibold text-gray-600 hover:bg-gray-50"
              >
                Resend
              </button>
              <button
                type="button"
                onClick={handleVerify}
                disabled={busy}
                className="flex-1 bg-[#6B0F12] text-white rounded-lg py-2 text-[13px] font-semibold hover:bg-[#7d1215] disabled:opacity-60 flex items-center justify-center gap-2"
              >
                {busy ? <><Spinner size="sm" /> Verifying…</> : "Verify"}
              </button>
            </div>
          </div>
        )}

        {/* Step: Verified */}
        {step === "verified" && (
          <div className="space-y-4 text-center">
            <div className="flex justify-center">
              <div className="w-14 h-14 rounded-full bg-green-100 flex items-center justify-center">
                <i className="fas fa-check-circle text-green-500 text-2xl" aria-hidden />
              </div>
            </div>
            <div>
              <p className="text-[14px] font-semibold text-gray-900">Access Verified</p>
              <p className="text-[13px] text-gray-500 mt-1">
                Your identity has been confirmed. You may now access the documents.
              </p>
            </div>
            <button
              type="button"
              onClick={onClose}
              className="w-full bg-[#6B0F12] text-white rounded-lg py-2 text-[13px] font-semibold hover:bg-[#7d1215]"
            >
              Close
            </button>
          </div>
        )}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main page
// ---------------------------------------------------------------------------

export default function DocumentsPage() {
  const { id: recordId } = useParams<{ id: string }>();
  const { user }  = useAuth();
  const addToast  = useUIStore((s) => s.addToast);

  const [slots,           setSlots]          = useState<SlotWithUploads[]>([]);
  const [record,          setRecord]         = useState<RecordDetail | null>(null);
  const [miscFiles,       setMiscFiles]      = useState<RecordFile[]>([]);
  const [loading,         setLoading]        = useState(true);
  const [uploading,       setUploading]      = useState<Record<number, boolean>>({});
  const [deletingUpload,  setDeletingUpload] = useState<number | null>(null);
  const [miscUploading,   setMiscUploading]  = useState(false);
  const [deletingFile,    setDeletingFile]   = useState<number | null>(null);
  const [resubmitting,    setResubmitting]   = useState(false);
  const [resubmitError,   setResubmitError]  = useState<string | null>(null);
  const [showPin,         setShowPin]        = useState(false);
  const [viewer,          setViewer]         = useState<{ blobUrl: string; filename: string } | null>(null);
  const [busyUploadId,    setBusyUploadId]   = useState<number | null>(null);
  const [busyFileId,      setBusyFileId]     = useState<number | null>(null);

  // Hidden file input for staff misc-file upload
  const miscInputRef = useRef<HTMLInputElement>(null);

  const load = useCallback(() => {
    if (!recordId) return;
    setLoading(true);
    Promise.all([
      documentsApi.slotsForRecord(Number(recordId)),
      recordsApi.detail(Number(recordId)),
      documentsApi.files(Number(recordId)),
    ])
      .then(([slotsRes, recordRes, filesRes]) => {
        setSlots(slotsRes.data);
        setRecord(recordRes.data);
        const fileList = Array.isArray(filesRes.data)
          ? filesRes.data
          : ((filesRes.data as unknown as { results: RecordFile[] }).results ?? []);
        setMiscFiles(fileList);
      })
      .finally(() => setLoading(false));
  }, [recordId]);

  useEffect(load, [load]);

  const isOwner   = record?.owners.some((o) => o.user === user?.id) ?? false;
  const isStaff   = user?.is_staff || user?.is_superuser;
  const canUpload =
    isOwner &&
    record != null &&
    UPLOAD_ALLOWED_STATUSES.includes(record.pipeline_status);

  // Non-owners who aren't staff can request a PIN
  const canPin = !isOwner && !isStaff && record != null;

  // ---------------------------------------------------------------------------
  // Slot upload
  // ---------------------------------------------------------------------------
  const handleUpload = async (slotId: number, files: File[]) => {
    if (!recordId || !files[0]) return;
    setUploading((prev) => ({ ...prev, [slotId]: true }));
    try {
      const { data } = await documentsApi.upload(Number(recordId), slotId, files[0]);
      addToast({
        type: "success",
        message: `File uploaded. Text extraction: ${data.extraction.status}.`,
      });
      load();
    } catch {
      addToast({ type: "error", message: "Upload failed. Please try again." });
    } finally {
      setUploading((prev) => ({ ...prev, [slotId]: false }));
    }
  };

  // ---------------------------------------------------------------------------
  // Misc file upload (staff only)
  // ---------------------------------------------------------------------------
  const handleMiscUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file || !recordId) return;
    setMiscUploading(true);
    try {
      await documentsApi.uploadRecordFile(Number(recordId), file);
      addToast({ type: "success", message: `"${file.name}" attached successfully.` });
      load();
    } catch {
      addToast({ type: "error", message: "Attachment failed. Please try again." });
    } finally {
      setMiscUploading(false);
      // Reset so the same file can be re-uploaded if needed
      if (miscInputRef.current) miscInputRef.current.value = "";
    }
  };

  // ---------------------------------------------------------------------------
  // Blob helpers for view / download (slot uploads and misc files)
  // ---------------------------------------------------------------------------
  const openViewer = (blobUrl: string, filename: string) => {
    setViewer({ blobUrl, filename });
  };

  const closeViewer = () => {
    if (viewer) URL.revokeObjectURL(viewer.blobUrl);
    setViewer(null);
  };

  const handleViewUpload = async (upload: RecordUpload) => {
    setBusyUploadId(upload.id);
    try {
      const { data } = await documentsApi.viewUpload(upload.id);
      openViewer(URL.createObjectURL(data as Blob), upload.slot_name ?? `v${upload.version}.pdf`);
    } catch {
      addToast({ type: "error", message: "Could not open document." });
    } finally {
      setBusyUploadId(null);
    }
  };

  const handleDownloadUpload = async (upload: RecordUpload) => {
    setBusyUploadId(upload.id);
    try {
      const { data } = await documentsApi.downloadUpload(upload.id);
      const url = URL.createObjectURL(data as Blob);
      const a   = document.createElement("a");
      a.href     = url;
      a.download = upload.slot_name ? `${upload.slot_name}_v${upload.version}.pdf` : `document_v${upload.version}.pdf`;
      a.click();
      URL.revokeObjectURL(url);
    } catch {
      addToast({ type: "error", message: "Download failed." });
    } finally {
      setBusyUploadId(null);
    }
  };

  const handleViewFile = async (file: RecordFile) => {
    setBusyFileId(file.id);
    try {
      const { data } = await documentsApi.viewFile(file.id);
      openViewer(URL.createObjectURL(data as Blob), file.filename);
    } catch {
      addToast({ type: "error", message: "Could not open file." });
    } finally {
      setBusyFileId(null);
    }
  };

  const handleDownloadFile = async (file: RecordFile) => {
    setBusyFileId(file.id);
    try {
      const { data } = await documentsApi.downloadFile(file.id);
      const url = URL.createObjectURL(data as Blob);
      const a   = document.createElement("a");
      a.href     = url;
      a.download = file.filename;
      a.click();
      URL.revokeObjectURL(url);
    } catch {
      addToast({ type: "error", message: "Download failed." });
    } finally {
      setBusyFileId(null);
    }
  };

  // ---------------------------------------------------------------------------
  // Slot upload delete (owner during revision — can remove a version they just uploaded)
  // ---------------------------------------------------------------------------
  const handleDeleteUpload = async (uploadId: number) => {
    setDeletingUpload(uploadId);
    try {
      await documentsApi.deleteUpload(uploadId);
      addToast({ type: "success", message: "Upload removed." });
      load();
    } catch {
      addToast({ type: "error", message: "Could not remove upload. Please try again." });
    } finally {
      setDeletingUpload(null);
    }
  };

  // ---------------------------------------------------------------------------
  // Resubmit for review (owner, when record is declined)
  // ---------------------------------------------------------------------------
  const handleResubmit = async () => {
    if (!recordId) return;
    setResubmitting(true);
    setResubmitError(null);
    try {
      await reviewsApi.resubmit(Number(recordId));
      const { data } = await recordsApi.detail(Number(recordId));
      setRecord(data);
      addToast({ type: "success", message: "Record resubmitted for review." });
    } catch (err: unknown) {
      const msg =
        (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail ??
        "Resubmission failed. Please try again.";
      setResubmitError(msg);
    } finally {
      setResubmitting(false);
    }
  };

  // ---------------------------------------------------------------------------
  // Misc file delete (staff: any; owner: only own uploads)
  // ---------------------------------------------------------------------------
  const handleDeleteFile = async (file: RecordFile) => {
    const canDelete =
      isStaff || (isOwner && file.uploaded_by === user?.id);
    if (!canDelete) return;

    setDeletingFile(file.id);
    try {
      await documentsApi.deleteFile(file.id);
      addToast({ type: "success", message: `"${file.filename}" removed.` });
      setMiscFiles((prev) => prev.filter((f) => f.id !== file.id));
    } catch {
      addToast({ type: "error", message: "Delete failed. Please try again." });
    } finally {
      setDeletingFile(null);
    }
  };

  if (loading) return <Skeleton />;

  return (
    <div>
      <PageHeader
        title="Documents"
        description="Upload and manage documents for this research record."
        actions={
          <Link
            to={`/records/${recordId}`}
            className="inline-flex items-center gap-1.5 px-3 py-2 rounded-lg border border-gray-200 text-[12px] font-semibold text-gray-600 hover:bg-gray-50 transition-colors"
          >
            <i className="fas fa-arrow-left text-[11px]" aria-hidden />
            Back to Record
          </Link>
        }
      />

      {/* PIN access banner for non-owners */}
      {canPin && (
        <div className="mb-4 px-5 py-4 bg-blue-50 border border-blue-200 rounded-xl flex items-center justify-between gap-4">
          <div>
            <p className="text-[13px] font-semibold text-blue-800">
              <i className="fas fa-lock mr-1.5" aria-hidden />
              Verified access
            </p>
            <p className="text-[12px] text-blue-600 mt-0.5">
              Request a one-time PIN to confirm your identity and access these documents.
            </p>
          </div>
          <button
            type="button"
            onClick={() => setShowPin(true)}
            className="flex-shrink-0 px-4 py-2 bg-blue-700 text-white text-[12px] font-semibold rounded-lg hover:bg-blue-800 transition-colors"
          >
            Request Access PIN
          </button>
        </div>
      )}

      {/* ------------------------------------------------------------------ */}
      {/* Slot-based uploads                                                  */}
      {/* ------------------------------------------------------------------ */}
      {slots.length === 0 ? (
        <EmptyState icon="fa-folder-open" title="No document slots defined." />
      ) : (
        <div className="flex flex-col gap-4">
          {slots.map((slot) => (
            <div key={slot.id} className="bg-white rounded-xl border border-gray-200 overflow-hidden">
              <div className="px-5 py-4 border-b border-gray-100 flex items-center justify-between">
                <div>
                  <p className="text-[14px] font-semibold text-gray-900">{slot.name}</p>
                  {slot.is_required && (
                    <Badge variant="danger" className="mt-1">Required</Badge>
                  )}
                </div>
                {slot.uploads.length > 0 && (
                  <Badge variant="success">v{slot.uploads[0].version} uploaded</Badge>
                )}
              </div>

              <div className="p-5">
                {/* Upload zone — owners only while record is editable, PDF only */}
                {canUpload && (
                  <FileUploadZone
                    onFiles={(files) => handleUpload(slot.id, files)}
                    accept=".pdf"
                    hint="PDF only, up to 50 MB"
                    disabled={uploading[slot.id]}
                  />
                )}

                {/* Version history */}
                {slot.uploads.length > 0 ? (
                  <div className={canUpload ? "mt-4" : ""}>
                    <p className="text-[12px] font-semibold text-gray-500 uppercase tracking-wide mb-2">
                      Version History
                    </p>
                    <table className="w-full text-[12px]">
                      <thead>
                        <tr className="border-b border-gray-100">
                          <th className="text-left py-1.5 text-gray-500 font-medium">Version</th>
                          <th className="text-left py-1.5 text-gray-500 font-medium">Uploaded By</th>
                          <th className="text-left py-1.5 text-gray-500 font-medium">Date</th>
                          <th className="text-left py-1.5 text-gray-500 font-medium">Status</th>
                          <th />
                        </tr>
                      </thead>
                      <tbody>
                        {slot.uploads.map((upload) => (
                          <tr key={upload.id} className="border-b border-gray-50">
                            <td className="py-1.5 text-gray-700">v{upload.version}</td>
                            <td className="py-1.5 text-gray-600">{upload.uploaded_by_name}</td>
                            <td className="py-1.5 text-gray-500">{formatDate(upload.created_at)}</td>
                            <td className="py-1.5">
                              <Badge variant={upload.status === "approved" ? "success" : "neutral"}>
                                {upload.status}
                              </Badge>
                            </td>
                            <td className="py-1.5 text-right">
                              <div className="flex items-center justify-end gap-2">
                                <button
                                  type="button"
                                  disabled={busyUploadId === upload.id}
                                  onClick={() => handleViewUpload(upload)}
                                  className="inline-flex items-center gap-1 px-2 py-1 rounded bg-gray-100 hover:bg-gray-200 text-[11px] font-medium text-gray-700 disabled:opacity-40 transition-colors"
                                  title="View in browser"
                                >
                                  {busyUploadId === upload.id ? <Spinner size="sm" /> : <i className="fas fa-eye" aria-hidden />}
                                  View
                                </button>
                                <button
                                  type="button"
                                  disabled={busyUploadId === upload.id}
                                  onClick={() => handleDownloadUpload(upload)}
                                  className="inline-flex items-center gap-1 px-2 py-1 rounded bg-gray-100 hover:bg-gray-200 text-[11px] font-medium text-gray-700 disabled:opacity-40 transition-colors"
                                  title="Download file"
                                >
                                  {busyUploadId === upload.id ? <Spinner size="sm" /> : <i className="fas fa-download" aria-hidden />}
                                  Download
                                </button>
                                {canUpload && (
                                  <button
                                    type="button"
                                    disabled={deletingUpload === upload.id}
                                    onClick={() => handleDeleteUpload(upload.id)}
                                    className="text-gray-500 hover:text-red-500 text-[12px] disabled:opacity-40 transition-colors"
                                    title="Remove this version"
                                  >
                                    {deletingUpload === upload.id
                                      ? <Spinner size="sm" />
                                      : <i className="fas fa-trash-alt" aria-hidden />
                                    }
                                  </button>
                                )}
                              </div>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                ) : (
                  !canUpload && (
                    <p className="text-[13px] text-gray-500 text-center py-4">
                      No files uploaded yet.
                    </p>
                  )
                )}
              </div>
            </div>
          ))}
        </div>
      )}

      {/* ------------------------------------------------------------------ */}
      {/* Miscellaneous Attachments (staff upload / everyone can view)        */}
      {/* ------------------------------------------------------------------ */}
      <div className="mt-6 bg-white rounded-xl border border-gray-200 overflow-hidden">
        <div className="px-5 py-4 border-b border-gray-100 flex items-center justify-between">
          <div>
            <p className="text-[14px] font-semibold text-gray-900">
              <i className="fas fa-paperclip mr-1.5 text-gray-500" aria-hidden />
              Supplementary Attachments
            </p>
            <p className="text-[12px] text-gray-500 mt-0.5">
              Additional files attached by staff (any file type).
            </p>
          </div>

          {/* Staff-only upload button */}
          {isStaff && (
            <div>
              <input
                ref={miscInputRef}
                type="file"
                className="hidden"
                onChange={handleMiscUpload}
              />
              <button
                type="button"
                disabled={miscUploading}
                onClick={() => miscInputRef.current?.click()}
                className="flex items-center gap-2 px-3 py-2 bg-[#6B0F12] text-white rounded-lg text-[12px] font-semibold hover:bg-[#7d1215] disabled:opacity-60 transition-colors"
              >
                {miscUploading
                  ? <><Spinner size="sm" /> Uploading…</>
                  : <><i className="fas fa-plus" aria-hidden /> Attach File</>
                }
              </button>
            </div>
          )}
        </div>

        <div className="p-5">
          {miscFiles.length === 0 ? (
            <p className="text-[13px] text-gray-500 text-center py-4">
              {isStaff
                ? "No supplementary files yet. Use the button above to attach one."
                : "No supplementary attachments have been added."}
            </p>
          ) : (
            <table className="w-full text-[13px]">
              <thead>
                <tr className="border-b border-gray-100">
                  <th className="text-left py-1.5 text-gray-500 font-medium text-[12px]">Filename</th>
                  <th className="text-left py-1.5 text-gray-500 font-medium text-[12px]">Uploaded By</th>
                  <th className="text-left py-1.5 text-gray-500 font-medium text-[12px]">Date</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {miscFiles.map((f) => {
                  const canDelete = isStaff || (isOwner && f.uploaded_by === user?.id);
                  const isPdf     = f.filename.toLowerCase().endsWith(".pdf");
                  const busy      = busyFileId === f.id;
                  return (
                    <tr key={f.id} className="border-b border-gray-50 hover:bg-gray-50">
                      <td className="py-2 pr-3">
                        <div className="flex items-center gap-2">
                          <i className="fas fa-file text-gray-500 text-[12px]" aria-hidden />
                          <span className="truncate max-w-[240px] text-[13px] text-gray-700">{f.filename}</span>
                        </div>
                      </td>
                      <td className="py-2 text-gray-600 pr-3 text-[12px]">
                        {f.uploaded_by_name ?? "—"}
                      </td>
                      <td className="py-2 text-gray-500 pr-3 text-[12px]">
                        {formatDate(f.created_at)}
                      </td>
                      <td className="py-2 text-right">
                        <div className="flex items-center justify-end gap-2">
                          {isPdf && (
                            <button
                              type="button"
                              disabled={busy}
                              onClick={() => handleViewFile(f)}
                              className="inline-flex items-center gap-1 px-2 py-1 rounded bg-gray-100 hover:bg-gray-200 text-[11px] font-medium text-gray-700 disabled:opacity-40 transition-colors"
                              title="View in browser"
                            >
                              {busy ? <Spinner size="sm" /> : <i className="fas fa-eye" aria-hidden />}
                              View
                            </button>
                          )}
                          <button
                            type="button"
                            disabled={busy}
                            onClick={() => handleDownloadFile(f)}
                            className="inline-flex items-center gap-1 px-2 py-1 rounded bg-gray-100 hover:bg-gray-200 text-[11px] font-medium text-gray-700 disabled:opacity-40 transition-colors"
                            title="Download file"
                          >
                            {busy ? <Spinner size="sm" /> : <i className="fas fa-download" aria-hidden />}
                            Download
                          </button>
                          {canDelete && (
                            <button
                              type="button"
                              disabled={deletingFile === f.id}
                              onClick={() => handleDeleteFile(f)}
                              className="text-gray-500 hover:text-red-500 text-[12px] disabled:opacity-40 transition-colors"
                              title="Remove attachment"
                            >
                              {deletingFile === f.id
                                ? <Spinner size="sm" />
                                : <i className="fas fa-trash-alt" aria-hidden />
                              }
                            </button>
                          )}
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          )}
        </div>
      </div>

      {/* Resubmit banner — shown to owners when record is declined */}
      {canUpload && record?.pipeline_status === "declined" && (
        <div className="mt-6 px-5 py-4 bg-amber-50 border border-amber-200 rounded-xl flex items-center justify-between gap-4">
          <div>
            <p className="text-[13px] font-semibold text-amber-800">
              <i className="fas fa-redo mr-1.5" aria-hidden />
              Ready to resubmit?
            </p>
            <p className="text-[12px] text-amber-700 mt-0.5">
              Upload your revised documents above, then click Resubmit to send the record back for review.
            </p>
            {resubmitError && (
              <p className="text-[12px] text-red-600 mt-1">{resubmitError}</p>
            )}
          </div>
          <button
            type="button"
            onClick={handleResubmit}
            disabled={resubmitting}
            className="flex-shrink-0 inline-flex items-center gap-1.5 px-4 py-2 rounded-lg bg-amber-600 text-white text-[12px] font-semibold hover:bg-amber-700 transition-colors disabled:opacity-60"
          >
            <i className="fas fa-redo text-[11px]" aria-hidden />
            {resubmitting ? "Resubmitting..." : "Resubmit for Review"}
          </button>
        </div>
      )}

      {/* PIN modal */}
      {showPin && record && user && (
        <AuthPinModal
          recordId={record.id}
          userEmail={user.email}
          onClose={() => setShowPin(false)}
        />
      )}

      {/* PDF viewer modal */}
      {viewer && (
        <PdfViewer
          blobUrl={viewer.blobUrl}
          filename={viewer.filename}
          onClose={closeViewer}
        />
      )}
    </div>
  );
}
