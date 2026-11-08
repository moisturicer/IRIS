/** The data notice and a person's answer, as the server sends them (IR-789, IR-790). */

export interface NoticeSection {
  title: string;
  body?: string;
  list?: string[];
}

export interface DataNotice {
  version: number;
  title: string;
  subtitle: string;
  sections: NoticeSection[];
  published_at: string;
}

export interface NoticeAnswer {
  version: number | null;
  ai_consent: boolean | null;
  answered_at: string | null;
}

export interface CurrentNotice extends DataNotice {
  /** Signed-in callers only. */
  answer?: NoticeAnswer | null;
  answer_required?: boolean;
}

export interface NoticeAnswerPayload {
  notice_version: number;
  agree_dpa: boolean;
  ai_consent: boolean;
  /** Required when a No becomes a Yes (ADR-054 decision 13, IR-791); ignored otherwise. */
  papers?: "all" | "from_now";
}
