import { apiClient } from "./client";
import type { NoticeAnswer, NoticeAnswerPayload, CurrentNotice, NoticeImpact, NoticeVersion } from "@/types/notice";

export type {
  DataNotice, NoticeAnswer, NoticeAnswerPayload, CurrentNotice, NoticeImpact, NoticeSection, NoticeVersion,
} from "@/types/notice";
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
  current: (opts?: { signal?: AbortSignal }) =>
    apiClient.get<CurrentNotice>("/auth/notice/", { signal: opts?.signal }),
  answer: (data: NoticeAnswerPayload) =>
    apiClient.post<{ answer: NoticeAnswer; answer_required: boolean }>("/auth/notice/answer/", data),

  // The Notices page (ADR-051 decisions 16-17 as amended by ADR-063 decision 9,
  // IR-799, IR-800). RDCO and the System Admin read the history; RDCO alone
  // publishes and reads the impact.
  versions: (opts?: { signal?: AbortSignal }) =>
    apiClient.get<NoticeVersion[]>("/auth/notice/versions/", { signal: opts?.signal }),
  impact: () => apiClient.get<NoticeImpact>("/auth/notice/versions/impact/"),
  /** 409 `notice_stale`, carrying the current notice, when a newer version exists than `based_on_version`. */
  publish: (data: { based_on_version: number; text: string }) =>
    apiClient.post<NoticeVersion>("/auth/notice/versions/", data),
};
