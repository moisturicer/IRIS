/** The data notice and a person's answer, as the server sends them (IR-789, IR-790). */

export interface NoticeSection {
  title: string;
  body?: string;
  list?: string[];
}

export interface DataNotice {
  version: number;
  /** The whole notice as plain text, for every version (IR-799). What IRIS shows (IR-800). */
  text: string;
  published_at: string;
  /** The older structured shape; kept by the server, read by no screen since IR-800. */
  title?: string;
  subtitle?: string;
  sections?: NoticeSection[];
}

/** One row of the version history, as RDCO and the System Admin read it (IR-799). */
export interface NoticeVersion extends DataNotice {
  published_by: { id: number; name: string; email: string } | null;
}

/** How many accounts a new version would make answer (IR-799). */
export interface NoticeImpact {
  current_version: number | null;
  accounts_to_answer: number;
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
