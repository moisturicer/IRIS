/**
 * Step 3 of the record creation/edit wizard.
 * Shows UploadSlots and lets the user upload one file per required slot.
 * Can be rendered without a recordId (AddRecord flow) -- in that case uploads
 * are queued locally and submitted after the record is created.
 *
 * TODO: persist staged files to sessionStorage so they survive accidental navigation.
 * TODO: show upload progress bar for large files.
 */
import { useEffect, useState } from "react";
import { documentsApi }    from "@/api/documents";
import { FileUploadZone }  from "@/components/shared/FileUploadZone";
import { Badge }           from "@/components/ui/Badge";
import { Spinner }         from "@/components/ui/Spinner";
import type { UploadSlot } from "@/types/documents";

interface UploadsStepProps {
  /** If provided, uploads go straight to the API for this record. */
  recordId?: number;
  /** Filter upload slots to only those configured for this record type. */
  recordTypeId?: number;
  /** Called whenever the local staged-file map changes (AddRecord flow). */
  onStagedChange?: (staged: Record<number, StagedFile>) => void;
}

export interface StagedFile {
  slotId:   number;
  file:     File;
  uploaded: boolean;
  error?:   string;
}

export function UploadsStep({ recordId, recordTypeId, onStagedChange }: UploadsStepProps) {
  const [slots, setSlots]         = useState<UploadSlot[]>([]);
  const [loading, setLoading]     = useState(true);
  const [staged, setStaged]       = useState<Record<number, StagedFile>>({});
  const [uploading, setUploading] = useState<Record<number, boolean>>({});

  useEffect(() => {
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
  }, [recordTypeId]);               // re-fetch when record type changes

  // Notify parent (AddRecordPage) whenever the staged map changes
  useEffect(() => {
    onStagedChange?.(staged);
  }, [staged, onStagedChange]);

  const stageFile = (slotId: number, files: File[]) => {
    if (!files[0]) return;
    setStaged((prev) => ({
      ...prev,
      [slotId]: { slotId, file: files[0], uploaded: false },
    }));

    // If we have a recordId, upload immediately
    if (recordId) {
      uploadNow(slotId, files[0]);
    }
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

  if (loading) {
    return (
      <div className="flex justify-center py-10">
        <Spinner />
      </div>
    );
  }

  if (slots.length === 0) {
    return (
      <p className="text-[13px] text-gray-500 text-center py-8">
        No document slots are configured for this record type.
      </p>
    );
  }

  return (
    <div className="flex flex-col gap-5">
      {!recordId && (
        <div className="px-4 py-3 bg-yellow-50 border border-yellow-200 rounded-xl text-[13px] text-yellow-700">
          <i className="fa fa-info-circle mr-2" />
          Files will be uploaded after the record is saved.
        </div>
      )}

      {slots.map((slot) => {
        const file    = staged[slot.id];
        const isUp    = uploading[slot.id];

        return (
          <div key={slot.id} className="border border-gray-200 rounded-xl overflow-hidden">
            <div className="flex items-center justify-between px-4 py-3 bg-gray-50 border-b border-gray-200">
              <div className="flex items-center gap-2">
                <span className="text-[13px] font-semibold text-gray-800">{slot.name}</span>
                {slot.is_required && <Badge variant="danger">Required</Badge>}
              </div>
              {file && (
                <Badge variant={file.uploaded ? "success" : file.error ? "danger" : "neutral"}>
                  {file.uploaded ? "Uploaded" : file.error ? "Error" : "Staged"}
                </Badge>
              )}
            </div>

            <div className="p-4">
              {isUp ? (
                <div className="flex justify-center py-6">
                  <Spinner />
                </div>
              ) : file && !file.error ? (
                <div className="flex items-center gap-3 px-3 py-2 bg-gray-50 rounded-lg border border-gray-200">
                  <i className="fa fa-file text-gray-400" />
                  <span className="text-[13px] text-gray-700 flex-1 truncate">{file.file.name}</span>
                  <button
                    type="button"
                    onClick={() => setStaged((prev) => {
                      const next = { ...prev };
                      delete next[slot.id];
                      return next;
                    })}
                    className="text-gray-400 hover:text-red-500 text-[12px]"
                  >
                    <i className="fa fa-times" />
                  </button>
                </div>
              ) : (
                <FileUploadZone
                  onFiles={(files) => stageFile(slot.id, files)}
                  accept=".pdf"
                  hint="PDF only, up to 50 MB"
                />
              )}
              {file?.error && (
                <p className="text-[12px] text-red-500 mt-1">{file.error}</p>
              )}
            </div>
          </div>
        );
      })}
    </div>
  );
}
