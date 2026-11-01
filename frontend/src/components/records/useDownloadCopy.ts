import { useState } from "react";

import { recordsApi } from "@/api/records";
import { downloadBlob, filenameFromDisposition } from "@/lib/utils";
import { useUIStore } from "@/store/ui.store";

/** A refused download's reason, read out of the blob axios hands back. */
async function refusalDetail(err: unknown): Promise<{ status?: number; detail?: string }> {
  const response = (err as { response?: { status?: number; data?: unknown } }).response;
  let detail: string | undefined;
  if (response?.data instanceof Blob) {
    try {
      detail = (JSON.parse(await response.data.text()) as { detail?: string }).detail;
    } catch {
      detail = undefined;
    }
  }
  return { status: response?.status, detail };
}

/**
 * Save a marked copy of a record through `/records/<id>/download/` (IR-676,
 * ADR-048), never the bytes the reader already holds. Shared by the paper
 * page and My Library's Download requests (IR-743). `onRefused` runs on a
 * 403, when access ended since the screen was loaded.
 */
export function useDownloadCopy(onRefused?: () => void) {
  const addToast = useUIStore((s) => s.addToast);
  const [saving, setSaving] = useState(false);

  const download = async (recordId: number) => {
    setSaving(true);
    try {
      const response = await recordsApi.downloadCopy(recordId);
      const name =
        filenameFromDisposition(response.headers?.["content-disposition"] as string | undefined)
        ?? `record-${recordId}.pdf`;
      downloadBlob(response.data, name);
    } catch (err) {
      const { status, detail } = await refusalDetail(err);
      addToast({ type: "error", message: detail ?? "The paper could not be downloaded. Please try again." });
      if (status === 403) onRefused?.();
    } finally {
      setSaving(false);
    }
  };

  return { saving, download };
}
