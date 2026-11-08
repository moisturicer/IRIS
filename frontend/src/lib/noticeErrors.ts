import type { DataNotice } from "@/types/notice";

/** The codes the server refuses with; a client keys off `code`, never the message (IR-789). */
export const ACCEPTANCE_REQUIRED_CODE = "notice_acceptance_required";
export const STALE_NOTICE_CODE = "notice_stale";

/** The newer notice a 409 `notice_stale` carries, or null for any other error. */
export function staleNoticeFrom(err: unknown): DataNotice | null {
  const response = (err as { response?: { status?: number; data?: { code?: string; notice?: DataNotice } } }).response;
  if (response?.status === 409 && response.data?.code === STALE_NOTICE_CODE && response.data.notice) {
    return response.data.notice;
  }
  return null;
}

/** True when the server refused because the current notice is unanswered. */
export function isAcceptanceRequired(err: unknown): boolean {
  const response = (err as { response?: { status?: number; data?: { code?: string } } }).response;
  return response?.status === 403 && response.data?.code === ACCEPTANCE_REQUIRED_CODE;
}
