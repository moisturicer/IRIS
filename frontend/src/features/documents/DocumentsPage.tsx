/**
 * Documents page -- lists UploadSlot requirements for a record and shows
 * upload history per slot. Accessible from the record detail page sidebar.
 *
 * TODO: hook into /api/v1/documents/ endpoints once backend is wired.
 * TODO: add version history panel (drawer) per slot.
 */
import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { documentsApi } from "@/api/documents";
import { PageHeader }   from "@/components/layout/PageHeader";
import { EmptyState }   from "@/components/shared/EmptyState";
import { FileUploadZone } from "@/components/shared/FileUploadZone";
import { Badge }        from "@/components/ui/Badge";
import { useUIStore }   from "@/store/ui.store";
import { formatDate }   from "@/lib/utils";
import type { RecordUpload, UploadSlot } from "@/types/documents";

interface SlotWithUploads extends UploadSlot {
  uploads: RecordUpload[];
}

export default function DocumentsPage() {
  const { id: recordId } = useParams<{ id: string }>();
  const addToast = useUIStore((s) => s.addToast);

  const [slots, setSlots]       = useState<SlotWithUploads[]>([]);
  const [loading, setLoading]   = useState(true);
  const [uploading, setUploading] = useState<Record<number, boolean>>({});

  const load = () => {
    if (!recordId) return;
    setLoading(true);
    documentsApi
      .slotsForRecord(Number(recordId))
      .then(({ data }) => setSlots(data))
      .finally(() => setLoading(false));
  };

  useEffect(load, [recordId]);

  const handleUpload = async (slotId: number, files: File[]) => {
    if (!recordId || !files[0]) return;
    setUploading((prev) => ({ ...prev, [slotId]: true }));
    try {
      await documentsApi.upload(Number(recordId), slotId, files[0]);
      addToast({ type: "success", message: "File uploaded successfully." });
      load();
    } catch {
      addToast({ type: "error", message: "Upload failed. Please try again." });
    } finally {
      setUploading((prev) => ({ ...prev, [slotId]: false }));
    }
  };

  if (loading) return <div className="p-8 text-center text-gray-400 text-[13px]">Loading...</div>;

  return (
    <div>
      <PageHeader
        title="Documents"
        description="Upload and manage documents for this research record."
      />

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
                {/* Latest upload status */}
                {slot.uploads.length > 0 && (
                  <Badge variant="success">
                    v{slot.uploads[0].version} uploaded
                  </Badge>
                )}
              </div>

              <div className="p-5">
                {/* Upload zone */}
                <FileUploadZone
                  onFiles={(files) => handleUpload(slot.id, files)}
                  accept=".pdf,.docx,.doc"
                  hint="PDF or DOCX, up to 50 MB"
                  disabled={uploading[slot.id]}
                />

                {/* Upload history */}
                {slot.uploads.length > 0 && (
                  <div className="mt-4">
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
                              <a
                                href={upload.file}
                                target="_blank"
                                rel="noreferrer"
                                className="text-[#6B0F12] hover:underline text-[12px]"
                              >
                                Download
                              </a>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
