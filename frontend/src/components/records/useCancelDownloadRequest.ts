import { useState } from "react";

import { recordsApi } from "@/api/records";
import { useUIStore } from "@/store/ui.store";

/**
 * Withdraw the reader's own pending download request (IR-688's endpoint,
 * offered by IR-743 on the paper page and in My Library). `onSettled` runs
 * either way: cancelled, or decided since the screen loaded, the state moved.
 */
export function useCancelDownloadRequest(onSettled?: () => void) {
  const addToast = useUIStore((s) => s.addToast);
  const [cancelling, setCancelling] = useState(false);

  const cancel = async (requestId: number) => {
    setCancelling(true);
    try {
      await recordsApi.cancelDownloadRequest(requestId);
      addToast({ type: "success", message: "Download request cancelled." });
    } catch (err) {
      const detail = (err as { response?: { data?: { detail?: string } } }).response?.data?.detail;
      addToast({ type: "error", message: detail ?? "The request could not be cancelled. Please try again." });
    } finally {
      setCancelling(false);
      onSettled?.();
    }
  };

  return { cancelling, cancel };
}
