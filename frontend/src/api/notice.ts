import { apiClient } from "./client";
import type { NoticeAnswer, NoticeAnswerPayload, CurrentNotice } from "@/types/notice";

export type { DataNotice, NoticeAnswer, NoticeAnswerPayload, CurrentNotice, NoticeSection } from "@/types/notice";
export { ACCEPTANCE_REQUIRED_CODE, STALE_NOTICE_CODE, isAcceptanceRequired, staleNoticeFrom } from "@/lib/noticeErrors";

/**
 * The data notice, read from the server (ADR-054 decisions 1-3, IR-789, IR-790).
 *
 * `GET /auth/notice/` is public, because registration shows it before there is
 * an account; a signed-in caller also gets their last `answer` and whether they
 * must answer now. The server keys every refusal off `code`, and so does the
 * client: `notice_acceptance_required` (403) means "show the notice screen",
 * `notice_stale` (409) carries the newer notice the person must read instead.
 */

export const noticeApi = {
  current: () => apiClient.get<CurrentNotice>("/auth/notice/"),
  answer: (data: NoticeAnswerPayload) =>
    apiClient.post<{ answer: NoticeAnswer; answer_required: boolean }>("/auth/notice/answer/", data),
};
